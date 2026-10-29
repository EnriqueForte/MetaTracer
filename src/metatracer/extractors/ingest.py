"""Ingestion pipeline: from confirmed targets to persisted raw metadata
(TASK-01, extended by TASK-09).

Flow per run: resolve targets -> crawl pages (depth 1) -> persist each HTML
page from the already-fetched body (no second GET) -> download child
documents/scripts through the safety gateway -> dedup by SHA-256 within the
run -> classify (magic bytes for PDF/image; HTML/JS only on non-document
URLs) -> extract (temp file for PDF/image; in-memory for HTML/JS) -> attach
allowlisted HTTP headers -> persist RawMetadataItem rows -> recompute
``Run.total_assets``.

One broken asset never aborts the run: every failure mode lands as
``extraction_status`` ``failed``/``skipped`` with a sanitized
``error_message``. File bytes live only in memory (bounded by
``max_file_bytes``) and in the temp file during extraction; they are never
written to the database or to ``data/``.

Downloads are sequential in the MVP: SQLite allows a single writer and the
per-domain rate limiter already paces requests (tasks README, known trap #6).
The shared download semaphore is still passed to the gateway so its contract
holds when concurrency is introduced.

If the process is killed between the temp-file write and the ``finally``
unlink, an orphan ``metatracer-*`` file remains in the OS temp dir.
:func:`sweep_stale_tempfiles` deletes those older than one hour at startup.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import (
    ExtractionError,
    MetaTracerError,
    OutOfScopeError,
    RedirectOutOfScopeError,
    ScopeNotConfirmedError,
    SecurityViolationError,
)
from metatracer.core.logging import sanitize_for_log, set_run_context
from metatracer.core.safety.guard import NetworkSafetyGuard
from metatracer.core.safety.http import (
    DomainRateLimiter,
    HttpTransportError,
    safe_httpx_request,
)
from metatracer.core.safety.scope import ScopeValidator
from metatracer.db.models import Asset, ExtractionStatus, RawMetadataItem, Run, SkipReason
from metatracer.db.repositories import AssetRepository, RawMetadataRepository, RunRepository
from metatracer.extractors.budget import LIMIT_BYTES, BudgetTracker, CrawlBudget
from metatracer.extractors.crawler import FetchedPage, PublicDocCrawler, reference_kind
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.headers import extract_http_headers
from metatracer.extractors.html import HtmlMetadataExtractor
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.javascript import JavaScriptMetadataExtractor
from metatracer.extractors.normalize import apply_normalization
from metatracer.extractors.office import NotOfficePackage, OfficeMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from metatracer.extractors.robots import (
    MAX_SITEMAP_FETCHES,
    MAX_SITEMAP_LOCS,
    ROBOTS_MAX_BYTES,
    SITEMAP_MAX_BYTES,
    RobotsPolicy,
    omission_message,
    parse_robots,
    parse_sitemap,
)
from metatracer.extractors.sniff import (
    SNIFF_HEADER_BYTES,
    AssetKind,
    classify_downloaded_asset,
    worth_fetching,
)
from metatracer.extractors.targets import TargetKind, TargetResolver

logger = logging.getLogger("metatracer.extractors.ingest")

_TEMP_PREFIX = "metatracer-"
_STALE_TEMP_SECONDS = 60 * 60


def sweep_stale_tempfiles(max_age_seconds: int = _STALE_TEMP_SECONDS) -> int:
    """Delete orphan ``metatracer-*`` files in the OS temp dir older than one hour.

    A crash between the download write and the ``finally`` unlink leaves the
    bytes on disk. Files younger than the window may still belong to a live
    scan and are left alone. Directories and unrelated names are not touched.
    """
    directory = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_seconds
    removed = 0
    try:
        entries = list(directory.glob(f"{_TEMP_PREFIX}*"))
    except OSError:
        return 0
    for path in entries:
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    if removed:
        logger.info("removed %d stale temporary file(s)", removed)
    return removed


# Fail-closed placeholder: an asset row exists between download and extraction;
# if the process dies in between, the row must not claim success.
_EXTRACTION_INCOMPLETE = "extraction did not complete"


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Counts of one ingestion phase, for the run log and the coverage view.

    ``limits_hit`` is the honest part: a run that stopped early says which
    budget stopped it, so "nothing else was found" can never be confused with
    "nothing else was looked at".
    """

    run_id: str
    targets_seen: int
    pages_crawled: int
    documents_discovered: int
    assets_ok: int
    assets_failed: int
    assets_skipped: int
    limits_hit: tuple[str, ...] = ()

    @property
    def total_assets(self) -> int:
        return self.assets_ok + self.assets_failed + self.assets_skipped


class _RobotsGate:
    """Per-run robots.txt courtesy. Never grants a host and never fails the run.

    One file is fetched per host, through ``safe_httpx_request``, and only
    after the caller has decided the crawl may still make a request. A
    failure (missing file, redirect out of scope, transport error, oversize)
    leaves an allow-all policy so the confirmed scope is still crawled.
    """

    def __init__(
        self,
        pipeline: IngestionPipeline,
        *,
        enabled: bool,
        scope: ScopeValidator,
        guard: NetworkSafetyGuard,
        rate_limiter: DomainRateLimiter,
        semaphore: asyncio.Semaphore,
        tracker: BudgetTracker,
        queue: list[str],
        probes: list[str],
        frontier: deque[tuple[str, int]],
        seen_pages: set[str],
    ) -> None:
        self._pipeline = pipeline
        self.enabled = enabled
        self._scope = scope
        self._guard = guard
        self._rate_limiter = rate_limiter
        self._semaphore = semaphore
        self._tracker = tracker
        self._queue = queue
        self._probes = probes
        self._frontier = frontier
        self._seen_pages = seen_pages
        self._policies: dict[str, RobotsPolicy] = {}
        self._omitted: set[str] = set()
        self._seeding = False
        self._sitemap_fetches = 0
        self._sitemap_locs = 0
        self.extra_documents = 0
        self._run: Run | None = None

    async def blocked(self, run: Run, url: str) -> bool:
        """True when ``url`` must not be requested. Records the omission once."""
        if not self.enabled:
            return False
        self._run = run
        if (await self._policy(url)).allows(url):
            return False
        await self._omit(run, url)
        return True

    async def _omit(self, run: Run, url: str) -> None:
        if url in self._omitted:
            return
        self._omitted.add(url)
        self._tracker.robots_omitted += 1
        await self._pipeline._simple_asset(
            run.id,
            url,
            ExtractionStatus.skipped,
            SkipReason.robots_disallow,
            omission_message(),
        )

    async def _policy(self, url: str) -> RobotsPolicy:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        scheme = (parts.scheme or "").lower()
        if not host or scheme not in ("http", "https"):
            return RobotsPolicy()
        cached = self._policies.get(host)
        if cached is not None:
            return cached
        body = await self._read_body(f"{scheme}://{host}/robots.txt", ROBOTS_MAX_BYTES)
        policy = parse_robots(body.decode("utf-8", errors="replace")) if body else RobotsPolicy()
        self._policies[host] = policy
        self._tracker.robots_checked = True
        if not self._seeding:
            self._seeding = True
            try:
                await self._seed(policy)
            finally:
                self._seeding = False
        return policy

    async def _seed(self, policy: RobotsPolicy) -> None:
        """Enqueue in-scope sitemap locations. Off-scope sitemap URLs are not requested."""
        pending = list(policy.sitemaps)
        while pending and self._sitemap_fetches < MAX_SITEMAP_FETCHES:
            url = pending.pop(0)
            if not _http_url(url):
                continue
            if not self._scope.is_in_scope(url):
                self._tracker.sitemaps_ignored += 1
                continue
            self._sitemap_fetches += 1
            body = await self._read_body(url, SITEMAP_MAX_BYTES)
            if body is None:
                continue
            kind, locs = parse_sitemap(body)
            if kind == "index":
                for loc in locs:
                    if not _http_url(loc):
                        continue
                    if self._scope.is_in_scope(loc):
                        pending.append(loc)
                    else:
                        self._tracker.sitemaps_ignored += 1
                continue
            for loc in locs:
                if self._sitemap_locs >= MAX_SITEMAP_LOCS:
                    self._tracker.sitemaps_truncated = True
                    return
                self._sitemap_locs += 1
                await self._enqueue(loc)
        if pending:
            self._tracker.sitemaps_truncated = True

    async def _enqueue(self, url: str) -> None:
        if not _http_url(url) or not self._scope.is_in_scope(url):
            if _http_url(url):
                self._tracker.sitemaps_ignored += 1
            return
        if (
            url in self._omitted
            or url in self._queue
            or url in self._probes
            or url in self._seen_pages
        ):
            return
        kind = reference_kind(url)
        if kind is None:
            return
        # Same-host policy is already cached. Another in-scope host is read,
        # but its own sitemaps are not followed while this seed is in progress.
        if self._run is None:
            return
        if not (await self._policy(url)).allows(url):
            await self._omit(self._run, url)
            return
        if kind == "page":
            self._frontier.append((url, 1))
            return
        if not self._tracker.charge_asset():
            return
        if kind == "probe":
            self._probes.append(url)
        else:
            self._queue.append(url)
        self.extra_documents += 1

    async def _read_body(self, url: str, limit: int) -> bytes | None:
        try:
            response = await safe_httpx_request(
                url,
                scope=self._scope,
                guard=self._guard,
                scope_confirmed=True,
                rate_limiter=self._rate_limiter,
                method="GET",
                max_file_bytes=limit,
                download_semaphore=self._semaphore,
            )
        except (MetaTracerError, HttpTransportError) as exc:
            logger.info(
                "robots/sitemap not applied for %s: %s",
                sanitize_for_log(url),
                sanitize_for_log(exc),
            )
            return None
        if response.too_large:
            self._tracker.charge_bytes(limit)
            logger.info(
                "robots/sitemap unreadable (over %d bytes): %s",
                limit,
                sanitize_for_log(url),
            )
            return None
        if response.status_code != 200 or not response.content:
            return None
        self._tracker.charge_bytes(len(response.content))
        return response.content


def _http_url(url: str) -> bool:
    return urlsplit(url).scheme.lower() in ("http", "https")


class IngestionPipeline:
    """Runs the TASK-01 ingestion phase for one persisted Run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        guard: NetworkSafetyGuard | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._guard = guard if guard is not None else NetworkSafetyGuard(settings.allow_loopback)

    async def execute(self, run_id: str) -> IngestionSummary:
        """Ingest every target of the run; never raises for per-asset failures."""
        run = await self._load_run(run_id)
        if not run.scope_confirmed:
            raise ScopeNotConfirmedError(
                "ingestion requires an explicitly confirmed scope (scope_confirmed=True)"
            )
        set_run_context(run.id)
        scope = ScopeValidator(_loads_str_list(run.allowed_scope, "allowed_scope"))
        raw_targets = _loads_str_list(run.target_input, "target_input")
        rate_limiter = DomainRateLimiter(self._settings.rate_limit_rps)
        # Fase 2: depth/pages/assets/bytes/seconds are explicit and recorded.
        # The budget comes from the run's persisted snapshot when present, so a
        # re-run keeps the limits the operator saw, and from Settings otherwise.
        budget = _budget_for(run, self._settings)
        tracker = BudgetTracker(budget=budget)
        semaphore = asyncio.Semaphore(budget.max_concurrency)
        resolver = TargetResolver(scope)
        crawler = PublicDocCrawler(scope=scope, guard=self._guard, rate_limiter=rate_limiter)

        queue, pages = self._classify_targets(resolver, raw_targets)
        documents_discovered = 0
        pages_crawled = 0
        preloaded: list[FetchedPage] = []
        probes: list[str] = []
        # BFS. Level 1 is an entry page. A linked ``.html`` is crawled only
        # while ``level < depth``; the page cap, the asset cap and the clock
        # still stop the walk. Default depth 1 therefore stays one hop.
        frontier: deque[tuple[str, int]] = deque((url, 1) for url in pages)
        seen_pages: set[str] = set()
        gate = _RobotsGate(
            self,
            enabled=budget.honor_robots,
            scope=scope,
            guard=self._guard,
            rate_limiter=rate_limiter,
            semaphore=semaphore,
            tracker=tracker,
            queue=queue,
            probes=probes,
            frontier=frontier,
            seen_pages=seen_pages,
        )
        while frontier:
            page_url, level = frontier.popleft()
            if page_url in seen_pages:
                continue
            seen_pages.add(page_url)
            if not tracker.check_deadline():
                logger.info("time budget reached; remaining pages not crawled")
                break
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info("byte budget reached; remaining pages not crawled")
                break
            # Courtesy before the page is requested. A missing robots.txt
            # allows the page; a Disallow records it and does not fetch it.
            if await gate.blocked(run, page_url):
                continue
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info(
                    "byte budget reached while reading robots.txt; remaining pages not crawled"
                )
                break
            if not tracker.charge_page():
                logger.info("page cap reached (%d); remaining pages not crawled", budget.max_pages)
                break
            remaining = budget.max_assets - len(queue) - len(preloaded) - len(probes)
            if remaining <= 0:
                tracker.note_asset_limit()
                logger.info(
                    "asset cap reached (%d); remaining pages not crawled", budget.max_assets
                )
                break
            fetched = await crawler.fetch_page(
                page_url,
                scope_confirmed=True,
                max_assets=max(remaining - 1, 0),
                download_semaphore=semaphore,
            )
            pages_crawled += 1
            if fetched is None:
                continue
            preloaded.append(fetched)
            # The crawler tells us whether the per-page cap cut the link scan;
            # if so, the asset limit was reached even when the queue looks full.
            if fetched.discovery_truncated:
                tracker.note_asset_limit()
            for url in fetched.child_urls:
                if url in queue:
                    continue
                if await gate.blocked(run, url):
                    continue
                if not tracker.charge_asset():
                    break
                queue.append(url)
                documents_discovered += 1
            for url in fetched.probe_urls:
                # Extensionless references are not downloaded yet: a HEAD
                # decides whether the declared type is a document.
                if url in queue or url in probes:
                    continue
                if await gate.blocked(run, url):
                    continue
                if not tracker.charge_asset():
                    break
                probes.append(url)
                documents_discovered += 1
            if level < budget.depth:
                for next_url in fetched.page_urls:
                    if next_url in seen_pages:
                        continue
                    if await gate.blocked(run, next_url):
                        continue
                    frontier.append((next_url, level + 1))
            elif fetched.page_urls:
                # Depth stopped the walk only when a further hop was allowed
                # by robots and still not taken. A Disallow is not a depth hit.
                further = False
                for next_url in fetched.page_urls:
                    if next_url in seen_pages:
                        continue
                    if await gate.blocked(run, next_url):
                        continue
                    further = True
                if further:
                    tracker.note_depth_limit()
        budget_assets = budget.max_assets - len(preloaded)
        if len(queue) > budget_assets:
            dropped = len(queue) - budget_assets
            # Truncating the queue is reaching the asset limit: record it so the
            # run cannot present a truncated crawl as a complete one.
            tracker.note_asset_limit()
            logger.info(
                "asset queue truncated at max_assets=%d (%d dropped)",
                budget.max_assets,
                dropped,
            )
            queue = queue[: max(budget_assets, 0)]

        seen_hashes = await self._known_hashes(run.id)
        ok = failed = skipped = 0
        for page in preloaded:
            if not tracker.check_deadline():
                break
            status = await self._process_preloaded(run, page, seen_hashes, tracker)
            tracker.assets_processed += 1
            if status is ExtractionStatus.ok:
                ok += 1
            elif status is ExtractionStatus.failed:
                failed += 1
            else:
                skipped += 1
        for url in probes:
            if not tracker.check_deadline():
                logger.info("time budget reached; %d probe(s) not checked", len(probes))
                break
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info("byte budget reached; remaining probes not checked")
                break
            if await gate.blocked(run, url):
                continue
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info(
                    "byte budget reached while reading robots.txt; remaining probes not checked"
                )
                break
            decision = await self._admit_probe(
                run, url, scope, rate_limiter, semaphore, tracker
            )
            if decision is None:
                status = await self._process_asset(
                    run, url, scope, rate_limiter, semaphore, seen_hashes, tracker
                )
            else:
                status = decision
            tracker.assets_processed += 1
            if status is ExtractionStatus.ok:
                ok += 1
            elif status is ExtractionStatus.failed:
                failed += 1
            else:
                skipped += 1
        for url in queue:
            if not tracker.check_deadline():
                # The queue was not emptied: that is a limit, not an empty target.
                logger.info("time budget reached; %d queued asset(s) not processed", len(queue))
                break
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info("byte budget reached; remaining assets not processed")
                break
            if await gate.blocked(run, url):
                continue
            if tracker.exhausted and LIMIT_BYTES in tracker.limits_hit:
                logger.info(
                    "byte budget reached while reading robots.txt; remaining assets not processed"
                )
                break
            status = await self._process_asset(
                run, url, scope, rate_limiter, semaphore, seen_hashes, tracker
            )
            tracker.assets_processed += 1
            if status is ExtractionStatus.ok:
                ok += 1
            elif status is ExtractionStatus.failed:
                failed += 1
            else:
                skipped += 1
        await self._finalize_run(run.id, tracker)
        summary = IngestionSummary(
            run_id=run.id,
            targets_seen=len(raw_targets),
            pages_crawled=pages_crawled,
            documents_discovered=documents_discovered + gate.extra_documents,
            assets_ok=ok,
            assets_failed=failed,
            assets_skipped=skipped + tracker.robots_omitted,
            limits_hit=tracker.limits_hit,
        )
        logger.info(
            "ingestion finished: %d assets (%d ok, %d failed, %d skipped), %d discovered, "
            "%d bytes, limits=%s",
            summary.total_assets,
            ok,
            failed,
            skipped,
            documents_discovered,
            tracker.bytes_downloaded,
            ",".join(tracker.limits_hit) or "none",
        )
        return summary

    def _classify_targets(
        self, resolver: TargetResolver, raw_targets: list[str]
    ) -> tuple[list[str], list[str]]:
        """Split targets into a document queue and a page list; bad targets are dropped."""
        queue: list[str] = []
        pages: list[str] = []
        for raw in raw_targets:
            try:
                target = resolver.resolve(raw)
            except (MetaTracerError, ValueError) as exc:
                logger.warning(
                    "target rejected: %s (%s)",
                    sanitize_for_log(raw),
                    sanitize_for_log(exc),
                )
                continue
            if target.kind is TargetKind.file:
                if target.url not in queue:
                    queue.append(target.url)
            elif target.url not in pages:
                pages.append(target.url)
        return queue, pages

    async def _admit_probe(
        self,
        run: Run,
        url: str,
        scope: ScopeValidator,
        rate_limiter: DomainRateLimiter,
        semaphore: asyncio.Semaphore,
        tracker: BudgetTracker,
    ) -> ExtractionStatus | None:
        """HEAD an extensionless URL. ``None`` means the body is worth a GET.

        A declared ``text/html`` (or anything else without an extractor) is
        recorded as ``skipped``/``unsupported_type`` and the body is never
        read. HEAD is not universal: 405/501 fall through to a normal download.
        """
        try:
            response = await safe_httpx_request(
                url,
                scope=scope,
                guard=self._guard,
                scope_confirmed=True,
                rate_limiter=rate_limiter,
                method="HEAD",
                max_file_bytes=self._settings.max_file_bytes,
                download_semaphore=semaphore,
            )
        except RedirectOutOfScopeError as exc:
            return await self._simple_asset(
                run.id, url, ExtractionStatus.skipped, SkipReason.out_of_scope, exc
            )
        except OutOfScopeError as exc:
            return await self._simple_asset(
                run.id, url, ExtractionStatus.skipped, SkipReason.out_of_scope, exc
            )
        except SecurityViolationError as exc:
            return await self._simple_asset(run.id, url, ExtractionStatus.failed, None, exc)
        except ScopeNotConfirmedError:
            raise
        except MetaTracerError as exc:
            return await self._simple_asset(run.id, url, ExtractionStatus.failed, None, exc)
        except HttpTransportError as exc:
            return await self._simple_asset(
                run.id, url, ExtractionStatus.failed, None, f"transport error: {type(exc).__name__}"
            )
        if response.status_code in (405, 501):
            return None
        content_type = (response.content_type or "").split(";", 1)[0].strip()
        if response.status_code >= 400:
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.failed,
                None,
                f"HTTP {response.status_code}",
                content_type=content_type,
            )
        declared = _declared_length(response.headers)
        if declared > self._settings.max_file_bytes:
            tracker.charge_bytes(declared)
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.too_large,
                f"declared size exceeds max_file_bytes ({self._settings.max_file_bytes})",
                content_type=content_type,
            )
        if not worth_fetching(response.content_type):
            shown = content_type or "none"
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.unsupported_type,
                f"declared content-type is not a supported document ({shown})",
                content_type=content_type,
            )
        return None

    async def _process_asset(
        self,
        run: Run,
        url: str,
        scope: ScopeValidator,
        rate_limiter: DomainRateLimiter,
        semaphore: asyncio.Semaphore,
        seen_hashes: set[str],
        tracker: BudgetTracker,
    ) -> ExtractionStatus:
        """Download, check and extract one document; persist its Asset row."""
        try:
            response = await safe_httpx_request(
                url,
                scope=scope,
                guard=self._guard,
                scope_confirmed=True,
                rate_limiter=rate_limiter,
                max_file_bytes=self._settings.max_file_bytes,
                download_semaphore=semaphore,
            )
        except RedirectOutOfScopeError as exc:
            # The hop was cancelled before the body was read (gateway contract).
            return await self._simple_asset(
                run.id, url, ExtractionStatus.skipped, SkipReason.out_of_scope, exc
            )
        except OutOfScopeError as exc:  # defense in depth; the resolver pre-validated
            return await self._simple_asset(
                run.id, url, ExtractionStatus.skipped, SkipReason.out_of_scope, exc
            )
        except SecurityViolationError as exc:
            # In-scope host resolving to a blocked address (e.g. DNS rebinding).
            return await self._simple_asset(run.id, url, ExtractionStatus.failed, None, exc)
        except ScopeNotConfirmedError:
            raise  # contract violation, not a per-asset failure: aborts the run
        except MetaTracerError as exc:
            # Base-class gateway errors (e.g. "redirect limit exceeded" from an
            # in-scope redirect loop): one broken asset must never kill the run.
            return await self._simple_asset(run.id, url, ExtractionStatus.failed, None, exc)
        except HttpTransportError as exc:
            return await self._simple_asset(
                run.id, url, ExtractionStatus.failed, None, f"transport error: {type(exc).__name__}"
            )

        final_url = response.url
        content_type = (response.content_type or "").split(";", 1)[0].strip()
        # Charge the transfer before any early return: the bytes already crossed
        # the wire, so the byte budget and the coverage total must see them.
        declared_bytes = max(len(response.content), _declared_length(response.headers))
        if not tracker.charge_bytes(declared_bytes):
            logger.info(
                "byte budget reached (%d of %d); %s not processed",
                tracker.bytes_downloaded,
                tracker.budget.max_total_bytes,
                sanitize_for_log(url),
            )
        if response.too_large:
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.too_large,
                f"body exceeds max_file_bytes ({self._settings.max_file_bytes})",
                final_url=final_url,
                content_type=content_type,
            )
        if response.status_code >= 400:
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.failed,
                None,
                f"HTTP {response.status_code}",
                final_url=final_url,
                content_type=content_type,
            )
        body = response.content
        if not body:
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.empty_body,
                "empty body",
                final_url=final_url,
                content_type=content_type,
            )
        digest = hashlib.sha256(body).hexdigest()
        if digest in seen_hashes:
            # The URL is still persisted for traceability; the bytes are not re-extracted.
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.duplicate_hash,
                "identical SHA-256 already processed in this run",
                final_url=final_url,
                content_type=content_type,
                file_hash=digest,
                file_size=len(body),
            )
        kind = classify_downloaded_asset(
            body[:SNIFF_HEADER_BYTES], content_type=content_type, url=final_url
        )
        if kind is None:
            return await self._simple_asset(
                run.id,
                url,
                ExtractionStatus.skipped,
                SkipReason.unsupported_type,
                f"magic bytes match no supported type (content-type: {content_type or 'none'})",
                final_url=final_url,
                content_type=content_type,
                file_hash=digest,
                file_size=len(body),
            )
        seen_hashes.add(digest)
        return await self._extract_asset(
            run.id,
            url,
            final_url,
            content_type,
            digest,
            body,
            kind,
            headers=response.headers,
        )

    async def _process_preloaded(
        self,
        run: Run,
        page: FetchedPage,
        seen_hashes: set[str],
        tracker: BudgetTracker,
    ) -> ExtractionStatus:
        """Persist a crawled HTML page from the body already in memory."""
        body = page.content
        tracker.charge_bytes(len(body))
        if not body:
            return await self._simple_asset(
                run.id,
                page.source_url,
                ExtractionStatus.skipped,
                SkipReason.empty_body,
                "empty body",
                final_url=page.url,
                content_type=page.content_type,
            )
        digest = hashlib.sha256(body).hexdigest()
        if digest in seen_hashes:
            return await self._simple_asset(
                run.id,
                page.source_url,
                ExtractionStatus.skipped,
                SkipReason.duplicate_hash,
                "identical SHA-256 already processed in this run",
                final_url=page.url,
                content_type=page.content_type,
                file_hash=digest,
                file_size=len(body),
            )
        seen_hashes.add(digest)
        return await self._extract_asset(
            run.id,
            page.source_url,
            page.url,
            page.content_type,
            digest,
            body,
            AssetKind.html,
            headers=page.headers,
        )

    async def _extract_asset(
        self,
        run_id: str,
        source_url: str,
        final_url: str,
        content_type: str,
        digest: str,
        body: bytes,
        kind: AssetKind,
        *,
        headers: dict[str, str] | None = None,
    ) -> ExtractionStatus:
        """Persist the asset (fail-closed), extract, store fields.

        PDF/image still go through a temp file (Pillow/pypdf). HTML and JS are
        extracted from the in-memory buffer so the page/script body never hits
        disk. Response headers (allowlisted) are attached to every ok asset.
        """
        temp_path: Path | None = None
        try:
            needs_temp = kind in {AssetKind.pdf, AssetKind.image}
            if needs_temp:
                with tempfile.NamedTemporaryFile(
                    mode="wb", delete=False, prefix="metatracer-"
                ) as handle:
                    handle.write(body)
                    temp_path = Path(handle.name)
            asset = await self._create_asset(
                run_id,
                source_url,
                final_url,
                content_type,
                digest,
                len(body),
                ExtractionStatus.failed,
                None,
                _EXTRACTION_INCOMPLETE,
            )
            try:
                fields = _extract_fields(kind, body, temp_path)
                fields.extend(extract_http_headers(headers or {}))
                fields = apply_normalization(fields)
            except NotOfficePackage as exc:
                await self._update_asset_status(
                    asset.id,
                    ExtractionStatus.skipped,
                    sanitize_for_log(exc, max_length=500),
                    skip_reason=SkipReason.unsupported_type,
                )
                return ExtractionStatus.skipped
            except ExtractionError as exc:
                await self._update_asset_status(
                    asset.id, ExtractionStatus.failed, sanitize_for_log(exc, max_length=500)
                )
                return ExtractionStatus.failed
            except Exception as exc:
                # Backstop: a broken parser must never kill the run.
                logger.warning(
                    "unexpected extractor error for %s: %s",
                    sanitize_for_log(source_url),
                    sanitize_for_log(type(exc).__name__),
                )
                await self._update_asset_status(
                    asset.id,
                    ExtractionStatus.failed,
                    f"unexpected extractor error: {type(exc).__name__}",
                )
                return ExtractionStatus.failed
            items = [
                RawMetadataItem(
                    asset_id=asset.id,
                    namespace=f.namespace,
                    key=f.key,
                    value=f.value,
                    value_normalized=f.value_normalized,
                    normalized_kind=f.normalized_kind,
                    timezone_status=f.timezone_status,
                )
                for f in fields
            ]
            if items:
                async with self._session_factory() as session:
                    await RawMetadataRepository(session).create_many(items)
            await self._update_asset_status(asset.id, ExtractionStatus.ok, None)
            return ExtractionStatus.ok
        finally:
            # The temp file is deleted even when extraction fails: file bytes
            # never outlive the asset's processing.
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("could not delete temp file: %s", sanitize_for_log(exc))

    async def _simple_asset(
        self,
        run_id: str,
        source_url: str,
        status: ExtractionStatus,
        skip_reason: SkipReason | None,
        error: object,
        *,
        final_url: str | None = None,
        content_type: str = "",
        file_hash: str = "",
        file_size: int = 0,
    ) -> ExtractionStatus:
        """Persist an asset that never reached extraction (skip/download failure)."""
        await self._create_asset(
            run_id,
            source_url,
            final_url or source_url,
            content_type,
            file_hash,
            file_size,
            status,
            skip_reason,
            sanitize_for_log(error, max_length=500),
        )
        if status is ExtractionStatus.skipped:
            logger.info(
                "asset skipped (%s): %s",
                skip_reason,
                sanitize_for_log(source_url),
            )
        else:
            logger.warning(
                "asset failed: %s (%s)",
                sanitize_for_log(source_url),
                sanitize_for_log(error),
            )
        return status

    async def _load_run(self, run_id: str) -> Run:
        async with self._session_factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")
        return run

    async def _known_hashes(self, run_id: str) -> set[str]:
        """SHA-256 digests already stored for this run (resumability).

        Hashes of extraction-failed assets are included on purpose: extraction
        is deterministic, so re-ingesting the same bytes would fail again —
        ``duplicate_hash`` is the honest outcome.
        """
        async with self._session_factory() as session:
            assets = await AssetRepository(session).list_by_run(run_id)
        return {asset.file_hash_sha256 for asset in assets if asset.file_hash_sha256}

    async def _create_asset(
        self,
        run_id: str,
        source_url: str,
        final_url: str,
        content_type: str,
        file_hash: str,
        file_size: int,
        status: ExtractionStatus,
        skip_reason: SkipReason | None,
        error_message: str | None,
    ) -> Asset:
        async with self._session_factory() as session:
            return await AssetRepository(session).create(
                Asset(
                    run_id=run_id,
                    source_url=source_url,
                    final_url=final_url,
                    content_type=content_type,
                    file_hash_sha256=file_hash,
                    file_size_bytes=file_size,
                    extraction_status=status,
                    skip_reason=skip_reason,
                    error_message=error_message,
                )
            )

    async def _update_asset_status(
        self,
        asset_id: str,
        status: ExtractionStatus,
        error_message: str | None,
        *,
        skip_reason: SkipReason | None = None,
    ) -> None:
        async with self._session_factory() as session:
            repo = AssetRepository(session)
            asset = await repo.get(asset_id)
            if asset is None:  # pragma: no cover - defensive; we just created it
                raise MetaTracerError("asset vanished during ingestion")
            asset.extraction_status = status
            asset.error_message = error_message
            if skip_reason is not None:
                asset.skip_reason = skip_reason
            await repo.update(asset)

    async def _finalize_run(self, run_id: str, tracker: BudgetTracker) -> None:
        """Recompute ``total_assets`` and persist the coverage snapshot.

        ``ingestion_stats`` is the durable half of the budget: the counters and
        the limits reached travel with the run, so the coverage endpoint and the
        report can say *why* a crawl stopped. Failure to write it must not fail
        the run (the assets are already stored), so it is logged and swallowed.
        """
        async with self._session_factory() as session:
            run_repo = RunRepository(session)
            assets = await AssetRepository(session).list_by_run(run_id)
            run = await run_repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; the run exists
                raise MetaTracerError("run vanished during ingestion")
            run.total_assets = len(assets)
            try:
                run.ingestion_stats = json.dumps(tracker.snapshot(), ensure_ascii=False)
            except (TypeError, ValueError):  # pragma: no cover - snapshot is plain JSON
                logger.warning("could not serialize ingestion stats; run keeps NULL")
            await run_repo.update(run)


def _extract_fields(
    kind: AssetKind, body: bytes, temp_path: Path | None
) -> list[ExtractedField]:
    """Dispatch to the extractor for ``kind``; HTML/JS never need a temp file."""
    if kind is AssetKind.pdf:
        if temp_path is None:  # pragma: no cover - guarded by caller
            raise ExtractionError("PDF extraction requires a temp file")
        return PdfMetadataExtractor().extract(temp_path)
    if kind is AssetKind.image:
        if temp_path is None:  # pragma: no cover - guarded by caller
            raise ExtractionError("image extraction requires a temp file")
        return ImageMetadataExtractor().extract(temp_path)
    if kind is AssetKind.html:
        return HtmlMetadataExtractor().extract(body)
    if kind is AssetKind.javascript:
        return JavaScriptMetadataExtractor().extract(body)
    if kind is AssetKind.office:
        return OfficeMetadataExtractor().extract(body)
    raise ExtractionError(f"unsupported asset kind: {kind}")


def _loads_str_list(payload: str, field_name: str) -> list[str]:
    """Parse a JSON list-of-strings column; corrupt rows fail the run loudly."""
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MetaTracerError(f"corrupt {field_name} JSON on run row") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MetaTracerError(f"corrupt {field_name} payload on run row: expected list of str")
    return value


def _budget_for(run: Run, settings: Settings) -> CrawlBudget:
    """The crawl budget of this run.

    A run row may carry the snapshot the operator configured (written by the
    orchestrator when a scan is created). When it does not — old rows, or a scan
    started before the budget existed — the budget is derived from Settings and
    clamped, which reproduces the historical behaviour (one page, the configured
    asset cap).
    """
    raw = getattr(run, "ingestion_stats", None)
    if isinstance(raw, str) and raw.strip():
        try:
            snapshot = json.loads(raw)
        except json.JSONDecodeError:
            snapshot = None
        if isinstance(snapshot, dict):
            configured = snapshot.get("budget")
            if isinstance(configured, dict):
                try:
                    return CrawlBudget(**configured)
                except (TypeError, ValueError):
                    # A corrupt snapshot must not abort the run: fall back to
                    # the settings-derived budget below.
                    logger.warning("ignoring corrupt budget snapshot on run %s", run.id)
    return CrawlBudget.from_settings(settings)


def _declared_length(headers: dict[str, str]) -> int:
    """``Content-Length`` as an int, or 0 when absent/not numeric.

    The body may have been aborted for size (``too_large``) with no bytes kept,
    so the declared length is the only evidence of the transfer cost.
    """
    raw = headers.get("content-length")
    if raw is None or not raw.isdigit():
        return 0
    return int(raw)
