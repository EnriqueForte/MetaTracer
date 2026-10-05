"""Shared finding filters for the API and CLI (TASK-08, subtask 8.2).

Presentation-layer only: the ReportBuilder still returns the full ordered
list; this module narrows it for exploration. Exported reports are never
filtered here — a bounty write-up stays complete.
"""

from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, Severity, TriageStatus
from metatracer.reports.builder import ReportFindingData


def filter_findings(
    findings: Sequence[ReportFindingData],
    *,
    severity: Severity | None = None,
    finding_type: FindingType | None = None,
    confidence: Confidence | None = None,
    q: str | None = None,
    triage: TriageStatus | None = None,
) -> list[ReportFindingData]:
    """Return findings matching every provided criterion (AND). Order is kept."""
    needle = q.strip().casefold() if q and q.strip() else ""
    matched: list[ReportFindingData] = []
    for finding in findings:
        if severity is not None and finding.severity is not severity:
            continue
        if triage is not None and finding.triage_status != triage:
            continue
        if finding_type is not None and finding.finding_type is not finding_type:
            continue
        if confidence is not None and finding.confidence is not confidence:
            continue
        if needle and needle not in _haystack(finding):
            continue
        matched.append(finding)
    return matched


def _haystack(finding: ReportFindingData) -> str:
    """Casefolded blob of the fields a hunter actually searches."""
    parts = (
        finding.title,
        finding.evidence,
        finding.field_source,
        finding.asset_source_url,
        finding.asset_final_url,
        finding.type_label,
    )
    return " ".join(parts).casefold()
