"""Pydantic response models for the REST API (TASK-06, subtask 6.3).

Enum values stay lowercase on the wire per the data contract; Title Case is a
presentation concern of the Web UI. These models are presentation mappings of
persisted rows / ReportBuilder output — no business logic lives here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from metatracer.db.models import (
    Asset,
    Confidence,
    ExtractionStatus,
    FindingType,
    ReasoningDepth,
    Run,
    RunStatus,
    Severity,
    SkipReason,
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

    @classmethod
    def from_models(cls, run: Run, assets: list[Asset]) -> RunStatusResponse:
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
        )


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
    """GET /api/runs: newest-first local history."""

    total: int
    runs: list[RunListItem]


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

    @classmethod
    def from_dashboard_stats(cls, stats: DashboardStats) -> DashboardStatsResponse:
        return cls(
            runs=stats.runs,
            assets=stats.assets,
            findings=stats.findings,
            top_domains=stats.top_domains,
            top_evidence=stats.top_evidence,
            agent_usage=stats.agent_usage,
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
