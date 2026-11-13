"""Severity rubric as code (TASK-03 subtask 3.1).

Single source of truth for the five-level severity contract. Consumed by:

1. The heuristic classifier of this package (offline baseline and fallback).
2. TASK-05: the agent system prompt embeds ``RUBRIC_PROMPT_TEXT`` and the
   post-LLM validator enforces ``HEURISTIC_CEILINGS`` via ``cap_severity`` —
   the guard may only lower or reject, never raise above the ceiling when the
   evidence has not changed.

The rubric is contextual: two findings of the same type may land on different
severities when the snippet differs. Context comes from the snippet itself and
from ``field_source`` / ``content_type`` / domain — never from external
knowledge (no OSINT, no geocoding, no CVE lookups).
"""

from metatracer.db.models import FindingType, Severity

# Ordering of the closed severity set; higher rank = more severe.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.info: 0,
    Severity.low: 1,
    Severity.medium: 2,
    Severity.high: 3,
    Severity.critical: 4,
}
RANK_TO_SEVERITY: dict[int, Severity] = {rank: sev for sev, rank in SEVERITY_RANK.items()}

# Mandatory heuristic ceilings (subtask 3.2.3). The heuristic never exceeds
# these, and the TASK-05 guard deescalates agent proposals above them when the
# snippet does not support more:
# - gps: the detector snippet is coordinates only, so critical is not offered.
#   The ceiling stays high. No geocoding and no "this is the CEO's home".
# - software_version: a name+version is never more than low; claiming an RCE
#   from the string "wkhtmltopdf" would be inventing exploitability.
# - email: a corporate address is at most medium.
# - internal_path: at most high (username / UNC share).
# - debug_comment: critical only with a secret marker in the snippet.
HEURISTIC_CEILINGS: dict[FindingType, Severity] = {
    FindingType.gps: Severity.high,
    FindingType.email: Severity.medium,
    FindingType.internal_path: Severity.high,
    FindingType.software_version: Severity.low,
    FindingType.debug_comment: Severity.critical,
    # An internal address in a metadata field is a lead, not a proven foothold.
    FindingType.internal_endpoint: Severity.medium,
    # The snippet is a storage URL. The product never requests it, so the
    # ceiling stays high: exposure of the bucket is for the analyst to check.
    FindingType.cloud_storage: Severity.high,
    # Closed-allowlist credential in extracted metadata (TASK-49).
    FindingType.secret: Severity.critical,
}


def ceiling_for(finding_type: FindingType) -> Severity:
    """Heuristic ceiling for a finding type (subtask 3.2.3)."""
    return HEURISTIC_CEILINGS[finding_type]


def cap_severity(severity: Severity, ceiling: Severity) -> Severity:
    """Return ``severity`` lowered to ``ceiling`` when it ranks above it."""
    if SEVERITY_RANK[severity] > SEVERITY_RANK[ceiling]:
        return ceiling
    return severity


# English rendering of the rubric table, embedded verbatim in the TASK-05
# system prompt. Reports and prompts are English per the data contract.
RUBRIC_PROMPT_TEXT = """\
SEVERITY RUBRIC (source of truth, TASK-03):

- critical: a secret or credential value is present in the evidence snippet
  (finding_type=secret: AWS key id AKIA, GitHub PAT ghp_, PEM private-key
  header, compact JWT; debug_comment: those plus "password=" / "api_key="
  with a value). The bare word "credentials" or "password" without a value
  is not critical. NOT enough: "CONFIDENTIAL".
- high: an internal path containing a username or an internal UNC share
  (e.g. "C:\\Users\\jdoe\\...", "\\\\CORP-DC01\\share\\..."), or precise GPS
  coordinates. GPS is never critical: the snippet is coordinates only and
  carries no home, person or facility name. NOT enough: "/var/www/html"
  with no user.
- medium: a personal corporate email (name.surname@company.com); a debug
  comment referencing a project/ticket/staging (e.g. "JIRA-8812"); a generic
  Unix deploy path ("/var/www/intranet"). A vendor address such as
  "@adobe.com" should never reach classification as a finding.
- low: a software name with a version number and nothing more
  ("Apache FOP 2.4", "Microsoft Word 16.0"). Never claim "vulnerable to
  CVE-..." without evidence in the snippet.
- info: empty, generic or weak evidence that the detector let through
  (an isolated "DRAFT" keyword, ambiguous strings). Never inflate a severity
  "just in case".

Heuristic ceilings: gps <= high; software_version <= low; email <= medium;
internal_path <= high; debug_comment <= critical (only with a secret marker
in the snippet); internal_endpoint <= medium; cloud_storage <= high (the
snippet is a storage URL and was not requested); secret <= critical (only
with a closed-allowlist pattern in the snippet). When evidence is ambiguous,
choose one level lower. Never raise severity without text in the snippet
that justifies it.
"""
