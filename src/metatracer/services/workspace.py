"""Run workspace: the read-only view of what a scan actually collected (Fase 1).

The detection pipeline only ever surfaced *findings*; everything else a run
extracted stayed in ``RawMetadataItem`` with no way to read it. This service is
the missing read path: assets, their raw metadata, and an honest coverage
summary, all strictly read-only.

Design notes:

- **No new business rules.** It composes the existing repositories; nothing is
  recomputed or reinterpreted. A value shown here is byte-for-byte the stored
  one (already sanitized and truncated by the extractors).
- **Keyset pagination.** Both listings paginate with the ``limit + 1`` probe so
  the caller learns ``has_more`` without an extra count. Filters are applied in
  SQL, never in Python over the whole run.
- **Coverage is honest about its own limits.** ``discovered``/``dropped`` are
  not persisted yet (that lands in Fase 2 with the crawl budget), so the summary
  reports what *is* stored and sets ``counters_recorded=False`` instead of
  inventing a number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import MetaTracerError
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import (
    Asset,
    ExtractionStatus,
    RawMetadataItem,
    Run,
    SkipReason,
)
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)

# Page ceilings. The API validates against the same bounds; the service clamps
# defensively so a direct caller cannot ask for an unbounded page.
MAX_ASSET_PAGE = 200
MAX_METADATA_PAGE = 500
DEFAULT_ASSET_PAGE = 50
DEFAULT_METADATA_PAGE = 100


@dataclass(frozen=True, slots=True)
class AssetPage:
    """One page of a run's assets plus the run-wide totals it belongs to."""

    run_id: str
    total: int
    assets: tuple[AssetSummary, ...]
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AssetSummary:
    """One asset as the inventory table shows it: no bytes, no metadata values."""

    id: str
    source_url: str
    final_url: str
    content_type: str
    file_hash_sha256: str
    file_size_bytes: int
    extraction_status: ExtractionStatus
    skip_reason: SkipReason | None
    error_message: str | None
    discovered_at: datetime
    metadata_fields: int
    findings: int


@dataclass(frozen=True, slots=True)
class MetadataPage:
    """One page of raw metadata rows, with the run-wide counts for the header."""

    run_id: str
    total: int
    items: tuple[MetadataEntry, ...]
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MetadataEntry:
    """A single stored field, with the asset it came from.

    ``value`` is the persisted sanitized text. ``truncated`` is derived from
    the extractor's marker (``sanitize.TRUNCATION_MARK``) rather than a new
    column, so it is available for every row already in the database.
    """

    id: int
    asset_id: str
    asset_url: str
    namespace: str
    key: str
    value: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """What the run collected, split the way the product must be honest about.

    ``counters_recorded`` is ``False`` for runs stored before Fase 2 (no
    ``ingestion_stats`` snapshot): the UI renders "discovery counters not
    recorded" instead of a zero that would read as "nothing was found". For a
    run recorded with a budget it is ``True`` and ``budget``/``limits_hit`` say
    exactly which limit stopped the crawl.
    """

    run_id: str
    status: str
    total_assets: int
    ok: int
    skipped: int
    failed: int
    bytes_downloaded: int
    metadata_fields: int
    findings: int
    by_skip_reason: dict[str, int] = field(default_factory=dict)
    by_namespace: dict[str, int] = field(default_factory=dict)
    counters_recorded: bool = False
    limits_hit: tuple[str, ...] = ()
    # Fase 2: the crawl budget actually applied to this run.
    budget: dict[str, int] = field(default_factory=dict)
    pages_crawled: int = 0
    assets_queued: int = 0
    elapsed_seconds: float = 0.0
    # None when the snapshot predates robots.txt accounting. False/0 is a run
    # that recorded the counters, not "we do not know".
    robots_checked: bool | None = None
    robots_omitted: int | None = None
    sitemaps_ignored: int | None = None
    sitemaps_truncated: bool | None = None


def encode_asset_cursor(asset: Asset) -> str:
    """``<discovered_at_iso>_<asset_id>``; mirrors the run-history encoding."""
    moment = asset.discovered_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    iso = moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"{iso}_{asset.id}"


class RunWorkspaceService:
    """Read-only composition over the repositories for one run's workspace."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _run(self, session: AsyncSession, run_id: str) -> Run:
        run = await RunRepository(session).get(run_id)
        if run is None:
            raise MetaTracerError(f"run not found: {sanitize_for_log(run_id)}")
        return run

    async def list_assets(
        self,
        run_id: str,
        *,
        status: ExtractionStatus | None = None,
        content_type: str | None = None,
        q: str | None = None,
        limit: int = DEFAULT_ASSET_PAGE,
        cursor: str | None = None,
    ) -> AssetPage:
        """One page of assets, with per-asset field and finding counts.

        Raises :class:`MetaTracerError` when the run does not exist and
        ``ValueError`` for a malformed cursor (the API maps it to 422).
        """
        page_size = min(max(limit, 1), MAX_ASSET_PAGE)
        async with self._session_factory() as session:
            await self._run(session, run_id)
            repo = AssetRepository(session)
            rows = await repo.page_by_run(
                run_id,
                status=status,
                content_type_prefix=content_type,
                q=q,
                limit=page_size,
                cursor=cursor,
            )
            total = await repo.count_by_run(run_id)
            finding_counts = await FindingRepository(session).counts_by_asset(run_id)
            field_counts = await RawMetadataRepository(session).counts_by_asset(run_id)
        has_more = len(rows) > page_size
        page = rows[:page_size]
        summaries = tuple(
            _asset_summary(
                asset,
                metadata_fields=field_counts.get(asset.id, 0),
                findings=finding_counts.get(asset.id, 0),
            )
            for asset in page
        )
        next_cursor = encode_asset_cursor(page[-1]) if has_more and page else None
        return AssetPage(
            run_id=run_id,
            total=total,
            assets=summaries,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def list_metadata(
        self,
        run_id: str,
        *,
        asset_id: str | None = None,
        namespace: str | None = None,
        key: str | None = None,
        q: str | None = None,
        limit: int = DEFAULT_METADATA_PAGE,
        cursor: str | None = None,
    ) -> MetadataPage:
        """One page of raw metadata, flattened with the owning asset's URL."""
        page_size = min(max(limit, 1), MAX_METADATA_PAGE)
        async with self._session_factory() as session:
            await self._run(session, run_id)
            repo = RawMetadataRepository(session)
            if asset_id is not None:
                asset = await AssetRepository(session).get(asset_id)
                # An asset of another run must not leak through this route.
                if asset is None or asset.run_id != run_id:
                    raise MetaTracerError(f"asset not found in run: {sanitize_for_log(asset_id)}")
            rows = await repo.page_by_run(
                run_id,
                asset_id=asset_id,
                namespace=namespace,
                key=key,
                q=q,
                limit=page_size,
                cursor=cursor,
            )
            total = await repo.count_by_run(
                run_id, asset_id=asset_id, namespace=namespace, q=q
            )
            urls = await _asset_urls(session, run_id)
        has_more = len(rows) > page_size
        page = rows[:page_size]
        items = tuple(
            _metadata_entry(item, asset_url=urls.get(item.asset_id, "")) for item in page
        )
        next_cursor = str(page[-1].id) if has_more and page else None
        return MetadataPage(
            run_id=run_id,
            total=total,
            items=items,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def coverage(self, run_id: str) -> CoverageSummary:
        """Counters of what this run stored, split by extraction status."""
        async with self._session_factory() as session:
            run = await self._run(session, run_id)
            assets = await AssetRepository(session).list_by_run(run_id)
            metadata_repo = RawMetadataRepository(session)
            namespace_counts = await metadata_repo.namespace_counts(run_id)
            metadata_fields = await metadata_repo.count_by_run(run_id)
            findings = await FindingRepository(session).counts_by_asset(run_id)

        ok = sum(1 for a in assets if a.extraction_status is ExtractionStatus.ok)
        skipped = sum(1 for a in assets if a.extraction_status is ExtractionStatus.skipped)
        failed = sum(1 for a in assets if a.extraction_status is ExtractionStatus.failed)
        by_reason: dict[str, int] = {}
        for asset in assets:
            if asset.skip_reason is not None:
                key = str(asset.skip_reason)
                by_reason[key] = by_reason.get(key, 0) + 1

        return CoverageSummary(
            run_id=run_id,
            status=str(run.status),
            total_assets=len(assets),
            ok=ok,
            skipped=skipped,
            failed=failed,
            bytes_downloaded=sum(asset.file_size_bytes for asset in assets),
            metadata_fields=metadata_fields,
            findings=sum(findings.values()),
            by_skip_reason=by_reason,
            by_namespace=dict(namespace_counts),
            **_recorded_counters(run),
        )


async def _asset_urls(session: AsyncSession, run_id: str) -> dict[str, str]:
    """``asset_id -> final_url`` for one run, in a single query."""
    result = await session.exec(
        select(Asset.id, Asset.final_url).where(Asset.run_id == run_id)
    )
    return {str(asset_id): str(url) for asset_id, url in result.all()}


def _recorded_counters(run: Run) -> dict[str, object]:
    """Coverage fields derived from ``Run.ingestion_stats`` (Fase 2).

    A run stored before the snapshot existed has ``ingestion_stats = NULL``;
    then ``counters_recorded`` stays false and the UI must say "not recorded".
    A snapshot written by ``_create_run`` but whose ingestion never ran (the run
    failed before downloading) is still recorded: the budget is known and
    ``limits_hit`` is empty, which is the truth.
    """
    raw = run.ingestion_stats
    if not isinstance(raw, str) or not raw.strip():
        return {"counters_recorded": False, "limits_hit": (), "budget": {}}
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError:
        return {"counters_recorded": False, "limits_hit": (), "budget": {}}
    if not isinstance(snapshot, dict):
        return {"counters_recorded": False, "limits_hit": (), "budget": {}}
    raw_limits = snapshot.get("limits_hit")
    limits = tuple(str(item) for item in raw_limits) if isinstance(raw_limits, list) else ()
    raw_budget = snapshot.get("budget")
    budget = (
        {
            str(key): int(value)
            for key, value in raw_budget.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        if isinstance(raw_budget, dict)
        else {}
    )
    pages = snapshot.get("pages_crawled")
    queued = snapshot.get("assets_queued")
    elapsed = snapshot.get("elapsed_seconds")
    return {
        "counters_recorded": bool(budget),
        "limits_hit": limits,
        "budget": budget,
        "pages_crawled": int(pages) if isinstance(pages, int) else 0,
        "assets_queued": int(queued) if isinstance(queued, int) else 0,
        "elapsed_seconds": float(elapsed) if isinstance(elapsed, (int, float)) else 0.0,
        "robots_checked": _optional_bool(snapshot, "robots_checked"),
        "robots_omitted": _optional_int(snapshot, "robots_omitted"),
        "sitemaps_ignored": _optional_int(snapshot, "sitemaps_ignored"),
        "sitemaps_truncated": _optional_bool(snapshot, "sitemaps_truncated"),
    }


def _optional_bool(snapshot: dict[str, object], key: str) -> bool | None:
    if key not in snapshot:
        return None
    value = snapshot[key]
    return value if isinstance(value, bool) else None


def _optional_int(snapshot: dict[str, object], key: str) -> int | None:
    if key not in snapshot:
        return None
    value = snapshot[key]
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _asset_summary(asset: Asset, *, metadata_fields: int, findings: int) -> AssetSummary:
    return AssetSummary(
        id=asset.id,
        source_url=asset.source_url,
        final_url=asset.final_url,
        content_type=asset.content_type,
        file_hash_sha256=asset.file_hash_sha256,
        file_size_bytes=asset.file_size_bytes,
        extraction_status=ExtractionStatus(asset.extraction_status),
        skip_reason=SkipReason(asset.skip_reason) if asset.skip_reason else None,
        error_message=asset.error_message,
        discovered_at=_as_utc(asset.discovered_at),
        metadata_fields=metadata_fields,
        findings=findings,
    )


def _metadata_entry(item: RawMetadataItem, *, asset_url: str) -> MetadataEntry:
    return MetadataEntry(
        id=int(item.id or 0),
        asset_id=item.asset_id,
        asset_url=asset_url,
        namespace=item.namespace,
        key=item.key,
        value=item.value,
        truncated=_is_truncated(item.value),
    )


def _is_truncated(value: str) -> bool:
    """True when the stored value carries the extractor's truncation marker.

    Imported lazily to keep this module free of extractor imports at load time
    (the marker is the single source of truth in ``extractors.sanitize``).
    """
    from metatracer.extractors.sanitize import TRUNCATION_MARK

    return value.endswith(TRUNCATION_MARK)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
