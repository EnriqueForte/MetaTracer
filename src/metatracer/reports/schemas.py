"""Pydantic schema of the exported JSON report (TASK-04, subtask 4.3.2).

The field set matches the task contract exactly. Enum fields reuse the closed
sets from :mod:`metatracer.db.models`, so invalid values fail validation and
``model_dump(mode="json")`` serializes them lowercase (StrEnum values).
``severity`` stays ``null`` for unclassified findings.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from metatracer.db.models import Confidence, FindingType, ReasoningDepth, Severity, TriageStatus
from metatracer.reports.builder import ReportData
from metatracer.reports.disclosure import (
    LIMITATIONS,
    METHODOLOGY,
    SCHEMA_VERSION,
)


class ReportSeverityCounts(BaseModel):
    """Severity tallies; unclassified counts findings whose severity is NULL."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    unclassified: int = 0


class ReportSummary(BaseModel):
    total_assets_scanned: int
    total_findings: int
    severity_counts: ReportSeverityCounts = Field(default_factory=ReportSeverityCounts)
    # Findings marked false_positive and left out of this report (TASK-35).
    excluded_false_positives: int = 0


class ReportFinding(BaseModel):
    """One finding card in the JSON export; enums serialize lowercase."""

    id: str
    type: FindingType
    severity: Severity | None = None  # null = unclassified
    confidence: Confidence
    asset_url: str
    field: str
    evidence: str
    impact: str
    explanation: str
    remediation: str
    reproduction_steps: list[str] = Field(default_factory=list)
    triage_status: TriageStatus = TriageStatus.open
    # JSON-only provenance. Scan findings are live fetches, never archive captures.
    historical: bool = False
    capture_date: str | None = None


class ReportCoverageDocument(BaseModel):
    """Crawl coverage copied into the export. Missing stats stay 'not recorded'."""

    counters_recorded: bool = False
    limits_hit: list[str] = Field(default_factory=list)
    pages_crawled: int = 0
    assets_queued: int = 0
    elapsed_seconds: float = 0.0
    statement: str = "Discovery counters were not recorded for this run."


class ReportDocument(BaseModel):
    """Root object of the exported JSON report (exact field set of 4.3.2)."""

    metatracer_version: str
    run_id: str
    target: str
    scope: list[str]
    generated_at: datetime  # serialized as ISO-8601 with Z suffix
    reasoning_depth: ReasoningDepth
    summary: ReportSummary
    findings: list[ReportFinding]
    compliance_notice: str
    # Fase 5 fields stay at the end so older readers that stop early still parse.
    schema_version: str = SCHEMA_VERSION
    methodology: str = METHODOLOGY
    coverage: ReportCoverageDocument = Field(default_factory=ReportCoverageDocument)
    limitations: str = LIMITATIONS
    redaction: str = "none"


def build_report_document(data: ReportData) -> ReportDocument:
    """Map the presentation-neutral :class:`ReportData` onto the JSON schema.

    ``asset_url`` is the asset's final URL (the public document actually
    fetched after in-scope redirects).
    """
    counts = data.severity_counts
    return ReportDocument(
        metatracer_version=data.metatracer_version,
        run_id=data.run_id,
        target=data.target,
        scope=list(data.scope),
        generated_at=data.generated_at,
        reasoning_depth=data.reasoning_depth,
        summary=ReportSummary(
            total_assets_scanned=data.total_assets,
            total_findings=data.total_findings,
            severity_counts=ReportSeverityCounts(
                critical=counts.critical,
                high=counts.high,
                medium=counts.medium,
                low=counts.low,
                info=counts.info,
                unclassified=counts.unclassified,
            ),
            excluded_false_positives=data.excluded_false_positives,
        ),
        findings=[
            ReportFinding(
                id=finding.id,
                type=finding.finding_type,
                severity=finding.severity,
                confidence=finding.confidence,
                asset_url=finding.asset_final_url,
                field=finding.field_source,
                evidence=finding.evidence,
                impact=finding.impact,
                explanation=finding.explanation,
                remediation=finding.remediation,
                reproduction_steps=list(finding.reproduction_steps),
                triage_status=finding.triage_status,
                historical=finding.historical,
                capture_date=finding.capture_date,
            )
            for finding in data.findings
        ],
        compliance_notice=data.compliance_notice,
        schema_version=SCHEMA_VERSION,
        methodology=METHODOLOGY,
        coverage=ReportCoverageDocument(
            counters_recorded=data.coverage.counters_recorded,
            limits_hit=list(data.coverage.limits_hit),
            pages_crawled=data.coverage.pages_crawled,
            assets_queued=data.coverage.assets_queued,
            elapsed_seconds=data.coverage.elapsed_seconds,
            statement=data.coverage.statement(),
        ),
        limitations=LIMITATIONS,
        redaction=data.redaction,
    )
