"""Global search over persisted findings and raw metadata (TASK-46).

Read-only: ILIKE on stored text, optional similar ranking via the existing
knowledge index. Never opens the network and never reads file bytes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.agents.knowledge import KnowledgeRetriever
from metatracer.core.exceptions import MetaTracerError
from metatracer.db.models import FindingType, Severity, TriageStatus
from metatracer.db.repositories import (
    _UNSET,
    FindingRepository,
    RawMetadataRepository,
    ScopeRepository,
)

_TYPE_LABELS: dict[FindingType, str] = {
    FindingType.gps: "GPS / Coordinates",
    FindingType.email: "Email",
    FindingType.internal_path: "Internal Path",
    FindingType.software_version: "Software Version",
    FindingType.debug_comment: "Debug Comment",
    FindingType.internal_endpoint: "Internal Endpoint",
    FindingType.cloud_storage: "Cloud Storage",
    FindingType.secret: "Secret",
}

SearchKind = Literal["findings", "metadata", "all"]
SearchMode = Literal["lexical", "similar"]

NAMESPACES = frozenset(
    {"exif", "xmp", "pdfinfo", "iptc", "http", "html", "js", "ooxml", "odf"}
)

DEFAULT_PAGE = 50
MAX_PAGE = 100


class ScopeLookupError(MetaTracerError):
    """``scope_id`` does not exist."""


@dataclass(frozen=True, slots=True)
class FindingHit:
    id: str
    run_id: str
    asset_id: str
    asset_url: str
    finding_type: FindingType
    type_label: str
    title: str | None
    field_source: str
    evidence_snippet: str
    severity: Severity | None
    triage_status: TriageStatus
    created_at: datetime
    score: float | None = None


@dataclass(frozen=True, slots=True)
class MetadataHit:
    id: int
    run_id: str
    asset_id: str
    asset_url: str
    namespace: str
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class FindingPage:
    total: int
    items: tuple[FindingHit, ...]
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MetadataPage:
    total: int
    items: tuple[MetadataHit, ...]
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    query: str
    kind: SearchKind
    mode: SearchMode
    findings: FindingPage
    metadata: MetadataPage


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def encode_finding_cursor(created_at: datetime, finding_id: str) -> str:
    iso = _as_utc(created_at).isoformat().replace("+00:00", "Z")
    return f"{iso}_{finding_id}"


class GlobalSearchService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        retriever: KnowledgeRetriever | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._retriever = retriever

    async def search(
        self,
        q: str,
        *,
        kind: SearchKind = "all",
        mode: SearchMode = "lexical",
        run_id: str | None = None,
        scope_id: str | None = None,
        finding_type: FindingType | None = None,
        namespace: str | None = None,
        severity: Severity | None | object = _UNSET,
        triage_status: TriageStatus | None = None,
        limit: int = DEFAULT_PAGE,
        findings_cursor: str | None = None,
        metadata_cursor: str | None = None,
    ) -> SearchResult:
        page_size = max(1, min(limit, MAX_PAGE))
        domains = await self._scope_domains(scope_id)
        similar_ids: tuple[str, ...] | None = None
        effective_mode: SearchMode = "lexical"
        if kind in ("findings", "all") and mode == "similar":
            similar_ids, used = await self._similar_ids(
                q, finding_type=finding_type, limit=page_size
            )
            if used:
                effective_mode = "similar"

        empty_findings = FindingPage(total=0, items=(), has_more=False, next_cursor=None)
        empty_metadata = MetadataPage(total=0, items=(), has_more=False, next_cursor=None)
        findings = empty_findings
        metadata = empty_metadata
        async with self._session_factory() as session:
            if kind in ("findings", "all"):
                findings = await self._findings_page(
                    session,
                    q=q,
                    run_id=run_id,
                    scope_domains=domains,
                    finding_type=finding_type,
                    severity=severity,
                    triage_status=triage_status,
                    limit=page_size,
                    cursor=None if similar_ids is not None else findings_cursor,
                    finding_ids=similar_ids,
                )
            if kind in ("metadata", "all"):
                metadata = await self._metadata_page(
                    session,
                    q=q,
                    run_id=run_id,
                    scope_domains=domains,
                    namespace=namespace,
                    limit=page_size,
                    cursor=metadata_cursor,
                )
        return SearchResult(
            query=q,
            kind=kind,
            mode=effective_mode,
            findings=findings,
            metadata=metadata,
        )

    async def _scope_domains(self, scope_id: str | None) -> tuple[str, ...]:
        if not scope_id:
            return ()
        async with self._session_factory() as session:
            scope = await ScopeRepository(session).get(scope_id)
        if scope is None:
            raise ScopeLookupError(f"scope not found: {scope_id}")
        parsed = json.loads(scope.domains)
        if not isinstance(parsed, list):
            return ()
        return tuple(str(item) for item in parsed if str(item).strip())

    async def _similar_ids(
        self,
        q: str,
        *,
        finding_type: FindingType | None,
        limit: int,
    ) -> tuple[tuple[str, ...] | None, bool]:
        if self._retriever is None:
            return None, False
        hits = await self._retriever.search_similar(
            q, finding_type=finding_type, limit=limit
        )
        if not hits:
            return None, False
        return tuple(hit.finding_id for hit in hits), True

    async def _findings_page(
        self,
        session: AsyncSession,
        **kwargs: object,
    ) -> FindingPage:
        repo = FindingRepository(session)
        rows = await repo.search_global(**kwargs)  # type: ignore[arg-type]
        total = await repo.count_global(
            q=str(kwargs["q"]),
            run_id=kwargs.get("run_id"),  # type: ignore[arg-type]
            scope_domains=kwargs.get("scope_domains", ()),  # type: ignore[arg-type]
            finding_type=kwargs.get("finding_type"),  # type: ignore[arg-type]
            severity=kwargs.get("severity", _UNSET),
            triage_status=kwargs.get("triage_status"),  # type: ignore[arg-type]
            finding_ids=kwargs.get("finding_ids"),  # type: ignore[arg-type]
        )
        limit = int(kwargs["limit"])  # type: ignore[arg-type]
        has_more = len(rows) > limit
        page = rows[:limit]
        items = tuple(
            FindingHit(
                id=finding.id,
                run_id=finding.run_id,
                asset_id=finding.asset_id,
                asset_url=asset.final_url or asset.source_url,
                finding_type=FindingType(finding.finding_type),
                type_label=_TYPE_LABELS[FindingType(finding.finding_type)],
                title=finding.title,
                field_source=finding.field_source,
                evidence_snippet=finding.evidence_snippet,
                severity=Severity(finding.severity) if finding.severity else None,
                triage_status=TriageStatus(finding.triage_status),
                created_at=_as_utc(finding.created_at),
            )
            for finding, asset in page
        )
        next_cursor = (
            encode_finding_cursor(page[-1][0].created_at, page[-1][0].id)
            if has_more and page
            else None
        )
        if kwargs.get("finding_ids") is not None:
            next_cursor = None
            has_more = False
        return FindingPage(total=total, items=items, has_more=has_more, next_cursor=next_cursor)

    async def _metadata_page(
        self,
        session: AsyncSession,
        **kwargs: object,
    ) -> MetadataPage:
        repo = RawMetadataRepository(session)
        rows = await repo.search_global(**kwargs)  # type: ignore[arg-type]
        total = await repo.count_global(
            q=str(kwargs["q"]),
            run_id=kwargs.get("run_id"),  # type: ignore[arg-type]
            scope_domains=kwargs.get("scope_domains", ()),  # type: ignore[arg-type]
            namespace=kwargs.get("namespace"),  # type: ignore[arg-type]
        )
        limit = int(kwargs["limit"])  # type: ignore[arg-type]
        has_more = len(rows) > limit
        page = rows[:limit]
        items = tuple(
            MetadataHit(
                id=item.id or 0,
                run_id=run_id,
                asset_id=asset.id,
                asset_url=asset.final_url or asset.source_url,
                namespace=item.namespace,
                key=item.key,
                value=item.value,
            )
            for item, asset, run_id in page
        )
        next_cursor = str(page[-1][0].id) if has_more and page else None
        return MetadataPage(total=total, items=items, has_more=has_more, next_cursor=next_cursor)
