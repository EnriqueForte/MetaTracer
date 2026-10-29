"""Methodology, coverage, limitations and file-only redaction (Fase 5).

Redaction rewrites the exported copy. It never writes back to the database.
Apache Tika and MediaInfo are not sidecars: the limitations text says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from enum import StrEnum

from metatracer.db.models import FindingType
from metatracer.reports.builder import ReportCoverage, ReportData, ReportFindingData

SCHEMA_VERSION = "1.1"

METHODOLOGY = (
    "MetaTracer fetches public documents inside the confirmed scope, extracts "
    "structured metadata, and runs deterministic detectors. A heuristic classifier "
    "sets a baseline severity. An optional agent may adjust that severity inside "
    "the rubric. Findings in this file are observations from the live fetch, not "
    "confirmed vulnerabilities."
)

LIMITATIONS = (
    "The scan does not authenticate, render JavaScript, or run OCR. Audio and "
    "video are not extracted: Apache Tika and MediaInfo are not used. Crawl depth, "
    "page count, asset count, bytes, and time stop at the recorded budget. A limit "
    "reached means later URLs were not fetched. Wayback and Common Crawl results, "
    "when an operator queries them, are index rows only. This report does not "
    "treat an archived URL as current exposure, and it does not download archive files."
)

PROVENANCE = (
    "Each finding names the live asset URL and the metadata field read from that "
    "fetch. capture_date is empty because the finding is not an archive capture. "
    "An empty capture date does not mean a historical URL is exposed now."
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_COORD_LABEL_RE = re.compile(
    r"(?i)\b(?:latitude|longitude|lat|lon|lng)\b\s*[:=]?\s*-?\d+(?:\.\d+)?"
)
_COORD_PAIR_RE = re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")


class Redaction(StrEnum):
    """How much of the exported file is rewritten. ``none`` is the default."""

    none = "none"
    contacts = "contacts"
    coordinates = "coordinates"
    all = "all"


def coverage_from_stats(raw: str | None) -> ReportCoverage:
    """Read the ingestion snapshot. NULL or unreadable JSON is 'not recorded'."""
    if not isinstance(raw, str) or not raw.strip():
        return ReportCoverage()
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError:
        return ReportCoverage()
    if not isinstance(snapshot, dict):
        return ReportCoverage()
    raw_budget = snapshot.get("budget")
    recorded = isinstance(raw_budget, dict) and any(
        isinstance(value, int) and not isinstance(value, bool) for value in raw_budget.values()
    )
    raw_limits = snapshot.get("limits_hit")
    limits = tuple(str(item) for item in raw_limits) if isinstance(raw_limits, list) else ()
    elapsed = snapshot.get("elapsed_seconds")
    seconds = (
        float(elapsed)
        if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool)
        else 0.0
    )
    return ReportCoverage(
        counters_recorded=recorded,
        limits_hit=limits,
        pages_crawled=_int_field(snapshot, "pages_crawled"),
        assets_queued=_int_field(snapshot, "assets_queued"),
        elapsed_seconds=seconds,
    )


def redaction_statement(mode: str) -> str:
    return (
        f"Redaction applied to this file: {mode}. "
        "Stored findings in the database were not modified."
    )


def disclosure_sections(data: ReportData) -> tuple[tuple[str, str], ...]:
    """Sections appended after the existing report body, in a fixed order."""
    return (
        ("Methodology", METHODOLOGY),
        ("Coverage", data.coverage.statement()),
        ("Limitations", LIMITATIONS),
        ("Provenance", PROVENANCE),
        ("Redaction", redaction_statement(data.redaction)),
    )


def apply_redaction(data: ReportData, mode: Redaction | str) -> ReportData:
    """Return a copy whose prose is redacted. The stored rows are not touched."""
    chosen = Redaction(mode)
    if chosen is Redaction.none:
        return replace(data, redaction=chosen.value)
    return replace(
        data,
        findings=tuple(_redact_finding(item, chosen) for item in data.findings),
        hygiene_note=_scrub(data.hygiene_note, chosen),
        redaction=chosen.value,
    )


def _redact_finding(finding: ReportFindingData, mode: Redaction) -> ReportFindingData:
    evidence = finding.evidence
    if mode in (Redaction.coordinates, Redaction.all) and finding.finding_type is FindingType.gps:
        evidence = "[redacted-coordinates]"
    return replace(
        finding,
        title=_scrub(finding.title, mode),
        evidence=_scrub(evidence, mode),
        impact=_scrub(finding.impact, mode),
        explanation=_scrub(finding.explanation, mode),
        remediation=_scrub(finding.remediation, mode),
        reproduction_steps=tuple(_scrub(step, mode) for step in finding.reproduction_steps),
        triage_note=_scrub(finding.triage_note, mode),
    )


def _scrub(text: str, mode: Redaction) -> str:
    if mode in (Redaction.contacts, Redaction.all):
        text = _EMAIL_RE.sub("[redacted-email]", text)
    if mode in (Redaction.coordinates, Redaction.all):
        text = _COORD_LABEL_RE.sub("[redacted-coordinates]", text)
        text = _COORD_PAIR_RE.sub("[redacted-coordinates]", text)
    return text


def _int_field(snapshot: dict[str, object], key: str) -> int:
    value = snapshot.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0
