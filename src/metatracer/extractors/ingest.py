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

Known limitation (accepted): if the process is killed between the temp-file
write and the ``finally`` unlink, an orphan ``metatracer-*`` file remains in
the OS temp dir until the OS cleans it. Startup-time sweeping of stale
``metatracer-*`` entries is possible later hardening, not MVP scope.
"""

import asyncio
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
    MAX_CONCURRENT_DOWNLOADS,
    DomainRateLimiter,
    HttpTransportError,
    safe_httpx_request,
)
from metatracer.core.safety.scope import ScopeValidator
from metatracer.db.models import Asset, ExtractionStatus, RawMetadataItem, Run, SkipReason
from metatracer.db.repositories import AssetRepository, RawMetadataRepository, RunRepository
from metatracer.extractors.crawler import FetchedPage, PublicDocCrawler
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.headers import extract_http_headers
from metatracer.extractors.html import HtmlMetadataExtractor
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.javascript import JavaScriptMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from metatracer.extractors.sniff import (
    SNIFF_HEADER_BYTES,
    AssetKind,
    classify_downloaded_asset,
)
from metatracer.extractors.targets import TargetKind, TargetResolver

logger = logging.getLogger("metatracer.extractors.ingest")

# Fail-closed placeholder: an asset row exists between download and extraction;
# if the process dies in between, the row must not claim success.
_EXTRACTION_INCOMPLETE = "extraction did not complete"


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Counts of one ingestion phase, for the run log and future UI progress."""

    run_id: str
    targets_seen: int
    pages_crawled: int
    documents_discovered: int
    assets_ok: int
    assets_failed: int
    assets_skipped: int

    @property
    def total_assets(self) -> int:
        return self.assets_ok + self.assets_failed + self.assets_skipped


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
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        resolver = TargetResolver(scope)
        crawler = PublicDocCrawler(scope=scope, guard=self._guard, rate_limiter=rate_limiter)

        queue, pages = self._classify_targets(resolver, raw_targets)
        documents_discovered = 0
        pages_crawled = 0
        preloaded: list[FetchedPage] = []
        for page_url in pages:
            # The HTML page itself consumes one slot of MAX_ASSETS_PER_RUN.
            remaining = self._settings.max_assets_per_run - len(queue) - len(preloaded)
            if remaining <= 0:
                logger.info(
                    "asset cap reached (%d); remaining pages not crawled",
                    self._settings.max_assets_per_run,
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
            for url in fetched.child_urls:
                if url not in queue:
                    queue.append(url)
                    documents_discovered += 1
        budget = self._settings.max_assets_per_run - len(preloaded)
        if len(queue) > budget:
            logger.info(
                "asset queue truncated at MAX_ASSETS_PER_RUN=%d (%d dropped)",
                self._settings.max_assets_per_run,
                len(queue) - budget,
            )
            queue = queue[: max(budget, 0)]

        seen_hashes = await self._known_hashes(run.id)
        ok = failed = skipped = 0
        for page in preloaded:
            status = await self._process_preloaded(run, page, seen_hashes)
            if status is ExtractionStatus.ok:
                ok += 1
            elif status is ExtractionStatus.failed:
                failed += 1
            else:
                skipped += 1
        for url in queue:
            status = await self._process_asset(
                run, url, scope, rate_limiter, semaphore, seen_hashes
            )
            if status is ExtractionStatus.ok:
                ok += 1
            elif status is ExtractionStatus.failed:
                failed += 1
            else:
                skipped += 1
        await self._finalize_run(run.id)
        summary = IngestionSummary(
            run_id=run.id,
            targets_seen=len(raw_targets),
            pages_crawled=pages_crawled,
            documents_discovered=documents_discovered,
            assets_ok=ok,
            assets_failed=failed,
            assets_skipped=skipped,
        )
        logger.info(
            "ingestion finished: %d assets (%d ok, %d failed, %d skipped), %d discovered",
            summary.total_assets,
            ok,
            failed,
            skipped,
            documents_discovered,
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

    async def _process_asset(
        self,
        run: Run,
        url: str,
        scope: ScopeValidator,
        rate_limiter: DomainRateLimiter,
        semaphore: asyncio.Semaphore,
        seen_hashes: set[str],
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
    ) -> ExtractionStatus:
        """Persist a crawled HTML page from the body already in memory."""
        body = page.content
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
                RawMetadataItem(asset_id=asset.id, namespace=f.namespace, key=f.key, value=f.value)
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
        self, asset_id: str, status: ExtractionStatus, error_message: str | None
    ) -> None:
        async with self._session_factory() as session:
            repo = AssetRepository(session)
            asset = await repo.get(asset_id)
            if asset is None:  # pragma: no cover - defensive; we just created it
                raise MetaTracerError("asset vanished during ingestion")
            asset.extraction_status = status
            asset.error_message = error_message
            await repo.update(asset)

    async def _finalize_run(self, run_id: str) -> None:
        """Recompute Run.total_assets once the ingestion phase ends."""
        async with self._session_factory() as session:
            run_repo = RunRepository(session)
            assets = await AssetRepository(session).list_by_run(run_id)
            run = await run_repo.get(run_id)
            if run is None:  # pragma: no cover - defensive; the run exists
                raise MetaTracerError("run vanished during ingestion")
            run.total_assets = len(assets)
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
