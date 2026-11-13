"""Pydantic response models for the REST API (TASK-06, subtask 6.3).

Enum values stay lowercase on the wire per the data contract; Title Case is a
presentation concern of the Web UI. These models are presentation mappings of
persisted rows / ReportBuilder output — no business logic lives here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    FindingType,
    ReasoningDepth,
    Run,
    RunStatus,
    Severity,
    SkipReason,
    TriageStatus,
)
from metatracer.reports.builder import ReportFindingData
from metatracer.services.dashboard import DashboardStats
from metatracer.services.notifications import NotificationEvent


class RunCreatedResponse(BaseModel):
    """202 body of POST /api/runs."""

    run_id: str


class AssetIssue(BaseModel):
    """One failed/skipped asset, surfaced so a broken asset is never invisible."""

    asset_id: str
    source_url: str
    status: ExtractionStatus  # failed | skipped
    skip_reason: SkipReason | None
    error_message: str | None


class RunStatusResponse(BaseModel):
    """GET /api/runs/{run_id}: status, counters, timestamps and asset issues.

    ``asset_issues`` feeds the collapsible "Asset issues" section of the
    dashboard (6.4): the simplest place for it, since the page already polls
    this endpoint.
    """

    run_id: str
    status: RunStatus
    target: str
    scope: list[str]
    reasoning_depth: ReasoningDepth
    total_assets: int
    total_findings: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    asset_issues: list[AssetIssue]
    # Fase 3. Null when the run is not grouped. The name is a label, not a
    # permission boundary.
    investigation_id: str | None = None
    investigation_name: str | None = None
    # TASK-50: previous completed run of the same scope snapshot, for compare.
    previous_run_id: str | None = None

    @classmethod
    def from_models(
        cls,
        run: Run,
        assets: list[Asset],
        *,
        investigation_name: str | None = None,
        previous_run_id: str | None = None,
    ) -> RunStatusResponse:
        """Map persisted rows; JSON text columns are decoded defensively."""
        targets = _json_str_list(run.target_input)
        issues = [
            AssetIssue(
                asset_id=asset.id,
                source_url=asset.source_url,
                status=ExtractionStatus(asset.extraction_status),
                skip_reason=SkipReason(asset.skip_reason) if asset.skip_reason else None,
                error_message=asset.error_message,
            )
            for asset in assets
            if ExtractionStatus(asset.extraction_status) is not ExtractionStatus.ok
        ]
        return cls(
            run_id=run.id,
            status=RunStatus(run.status),
            target=targets[0] if targets else "unknown",
            scope=_json_str_list(run.allowed_scope),
            reasoning_depth=ReasoningDepth(run.reasoning_depth),
            total_assets=run.total_assets,
            total_findings=run.total_findings,
            error_message=run.error_message,
            started_at=_as_utc(run.started_at),
            completed_at=_as_utc(run.completed_at) if run.completed_at else None,
            asset_issues=issues,
            investigation_id=run.investigation_id,
            investigation_name=investigation_name,
            previous_run_id=previous_run_id,
        )


class FindingResponse(BaseModel):
    """One finding card, mapped 1:1 from the ReportBuilder entry (parity)."""

    id: str
    title: str
    finding_type: FindingType
    type_label: str
    severity: Severity | None  # None = unclassified (sorts last, like the report)
    confidence: Confidence
    field_source: str
    evidence_snippet: str
    severity_justification: str
    impact_analysis: str
    remediation_advice: str
    reproduction_steps: list[str]
    asset_source_url: str
    asset_final_url: str
    asset_content_type: str
    # TASK-35 operator triage; independent of severity.
    triage_status: TriageStatus = TriageStatus.open
    triage_note: str | None = None
    triaged_by: str | None = None
    triaged_at: datetime | None = None
    # Fase 1: lets the workspace link a finding to the asset it came from and
    # show which detector produced it. Add-only, so existing clients are fine.
    asset_id: str = ""
    detector_method: DetectorMethod = DetectorMethod.rule
    created_at: datetime | None = None
    # Fase 3: a prior decision in the same investigation. Null means there is
    # nothing to suggest. The finding's own triage_status is unchanged.
    triage_suggestion: TriageSuggestionResponse | None = None

    @classmethod
    def from_report(cls, entry: ReportFindingData) -> FindingResponse:
        return cls(
            id=entry.id,
            title=entry.title,
            finding_type=entry.finding_type,
            type_label=entry.type_label,
            severity=entry.severity,
            confidence=entry.confidence,
            field_source=entry.field_source,
            evidence_snippet=entry.evidence,
            severity_justification=entry.explanation,
            impact_analysis=entry.impact,
            remediation_advice=entry.remediation,
            reproduction_steps=list(entry.reproduction_steps),
            asset_source_url=entry.asset_source_url,
            asset_final_url=entry.asset_final_url,
            asset_content_type=entry.asset_content_type,
            triage_status=entry.triage_status,
            triage_note=entry.triage_note or None,
            triaged_by=entry.triaged_by or None,
            triaged_at=entry.triaged_at,
            asset_id=entry.asset_id,
            detector_method=entry.detector_method,
            created_at=entry.created_at,
        )


class TriageSuggestionResponse(BaseModel):
    """A triage decision from another run in the same investigation.

    Display only. Applying it is a separate operator request and does not
    change severity or evidence.
    """

    status: TriageStatus
    from_run_id: str
    from_finding_id: str
    note: str | None = None
    triaged_at: datetime | None = None


class TriageRequest(BaseModel):
    """PUT /api/runs/{run_id}/findings/{finding_id}/triage body (TASK-35).

    Unknown keys are a 422: a client sending ``severity`` must not get a 200.
    """

    model_config = ConfigDict(extra="forbid")

    status: TriageStatus
    note: str | None = Field(default=None, max_length=500)


class TriageResponse(BaseModel):
    finding_id: str
    triage_status: TriageStatus
    triage_note: str | None
    triaged_by: str | None
    triaged_at: datetime | None
    severity: Severity | None
    evidence_snippet: str


class BulkTriageRequest(BaseModel):
    """POST /api/runs/{run_id}/findings/triage (TASK-42).

    Unknown keys are a 422. ``severity`` must never be accepted.
    """

    model_config = ConfigDict(extra="forbid")

    finding_ids: list[str] = Field(min_length=1, max_length=200)
    status: TriageStatus
    note: str | None = Field(default=None, max_length=500)


class BulkTriageResponse(BaseModel):
    updated: int
    missing: list[str]
    triage_status: TriageStatus
    findings: list[TriageResponse]


class FindingsResponse(BaseModel):
    """GET /api/runs/{run_id}/findings: the report-ordered list."""

    run_id: str
    total: int
    findings: list[FindingResponse]


class RunListItem(BaseModel):
    """One row of GET /api/runs (local history, TASK-08)."""

    run_id: str
    status: RunStatus
    target: str
    scope: list[str]
    total_assets: int
    total_findings: int
    started_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_run(cls, run: Run) -> RunListItem:
        targets = _json_str_list(run.target_input)
        return cls(
            run_id=run.id,
            status=RunStatus(run.status),
            target=targets[0] if targets else "unknown",
            scope=_json_str_list(run.allowed_scope),
            total_assets=run.total_assets,
            total_findings=run.total_findings,
            started_at=_as_utc(run.started_at),
            completed_at=_as_utc(run.completed_at) if run.completed_at else None,
        )


class RunListResponse(BaseModel):
    """GET /api/runs: newest-first local history (TASK-08).

    TASK-21 (v2.4): cursor pagination. ``total`` is the GLOBAL count of runs
    matching the filter (untruncated, so the UI says "N runs" honestly);
    ``runs`` is the current page; ``has_more``/``next_cursor`` drive the
    prev/next UI.
    """

    total: int  # global count matching the filter (never truncated by limit)
    runs: list[RunListItem]
    has_more: bool = False
    next_cursor: str | None = None

    @classmethod
    def from_page(
        cls, total: int, runs: list[RunListItem], has_more: bool, next_cursor: str | None
    ) -> RunListResponse:
        return cls(total=total, runs=runs, has_more=has_more, next_cursor=next_cursor)


class SeverityTrendPoint(BaseModel):
    """Findings created on one UTC day, by severity (TASK-35, block 35.4)."""

    date: str  # YYYY-MM-DD, UTC
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    unclassified: int = 0


class ComparedRun(BaseModel):
    run_id: str
    target: str
    status: RunStatus
    started_at: datetime
    total_findings: int


class ComparedFindingResponse(BaseModel):
    """One finding of a comparison. ``finding_id`` belongs to run ``b`` except for ``resolved``."""

    finding_id: str
    run_id: str
    finding_type: FindingType
    severity: Severity | None
    evidence_snippet: str
    asset_url: str
    triage_status: TriageStatus = TriageStatus.open
    # Set when the same finding is in both runs and the severity differs.
    # ``severity`` on this row is the reviewed run. Null means unclassified.
    previous_severity: Severity | None = None
    # Set on a reappeared finding: an earlier run of the same investigation.
    prior_run_id: str | None = None


class RunComparisonResponse(BaseModel):
    """GET /api/compare: how findings moved from the baseline to the reviewed run.

    ``resolved`` means absent from the reviewed run. It is not proof the
    finding is gone unless ``coverage_recorded_b`` is true and ``limits_hit_b``
    is empty.
    """

    a: ComparedRun
    b: ComparedRun
    new: list[ComparedFindingResponse]
    resolved: list[ComparedFindingResponse]
    persistent: list[ComparedFindingResponse]
    reappeared: list[ComparedFindingResponse] = []
    severity_changed: list[ComparedFindingResponse] = []
    limits_hit_a: list[str] = []
    limits_hit_b: list[str] = []
    coverage_recorded_a: bool = False
    coverage_recorded_b: bool = False


class DashboardStatsResponse(BaseModel):
    """GET /api/stats: one aggregated snapshot of the local data (TASK-11).

    Read-only and agent-agnostic: built entirely from persisted counters, so
    it works with zero runs and with zero agent_log rows.
    """

    runs: dict[str, int]
    assets: dict[str, int]
    findings: dict[str, Any]
    top_domains: list[dict[str, Any]]
    top_evidence: list[dict[str, Any]]
    agent_usage: dict[str, int]
    trends: list[SeverityTrendPoint] = []

    @classmethod
    def from_dashboard_stats(cls, stats: DashboardStats) -> DashboardStatsResponse:
        return cls(
            runs=stats.runs,
            assets=stats.assets,
            findings=stats.findings,
            top_domains=stats.top_domains,
            top_evidence=stats.top_evidence,
            agent_usage=stats.agent_usage,
            trends=[SeverityTrendPoint(**point) for point in stats.trends],
        )


class NotificationResponse(BaseModel):
    """One terminal-run notification (TASK-12, v2.0).

    ``kind`` reuses the ``run.status`` enum (``completed`` | ``failed``) and
    travels lowercase per the data contract; ``error_message`` is present only
    for ``failed`` (the orchestrator already sanitized it).
    """

    id: int  # queue index, stable within the process
    kind: RunStatus
    run_id: str
    target: str
    total_assets: int
    total_findings: int
    error_message: str | None
    created_at: datetime

    @classmethod
    def from_event(cls, event: NotificationEvent) -> NotificationResponse:
        return cls(
            id=event.id,
            kind=event.kind,
            run_id=event.run_id,
            target=event.target,
            total_assets=event.total_assets,
            total_findings=event.total_findings,
            error_message=event.error_message,
            created_at=_as_utc(event.created_at),
        )


class NotificationListResponse(BaseModel):
    """GET /api/notifications: the in-memory queue, newest first."""

    total: int
    notifications: list[NotificationResponse]


def _json_str_list(payload: str) -> list[str]:
    """Decode a JSON list-of-strings column; corrupt input degrades to []."""
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return [payload.strip()] if payload.strip() else []
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_cursor(started_at: datetime, run_id: str) -> str:
    """Build the stable keyset anchor ``<started_at_iso>_<run_id>``.

    ``started_at`` (already UTC-normalized) is serialized with microseconds;
    the UUID ``run_id`` is the tie-breaker that makes the ``(started_at, id)``
    composite key total. This is the exact shape ``_split_cursor`` in
    db/repositories.py parses. Keyset anchors stay stable under new inserts
    (unlike offset-based pagination).
    """
    # Use +00:00 like isoformat, then swap the plus for a %2B-safe ASCII
    # form: the cursor travels inside a query string where a raw "+" is
    # decoded as a space by form parsers. The underscore delimiter is
    # preserved; a hyphen-safe URL sees no ambiguity.
    iso = _as_utc(started_at).isoformat().replace("+00:00", "Z")
    return f"{iso}_{run_id}"
