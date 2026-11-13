"""Post-LLM evidence guard (TASK-05, subtask 5.2.3).

The prompt is not a guarantee; this deterministic validator is. It runs on
every model proposal before anything is persisted and it can only ever lower,
repair or reject — never raise a severity, never rewrite evidence.

Invariants applied (in order):

1. **Cited evidence must exist**: ``cited_evidence`` must be a substring of
   ``evidence_snippet`` after the same normalization the anchor layer uses
   (whitespace collapsed, casefolded). A hallucinated citation is replaced by
   the verbatim snippet and the severity drops one rank (ambiguity rule 3.2.2).
2. **Severity ceilings**: the proposal is capped at the TASK-03 per-type
   ceiling (``HEURISTIC_CEILINGS``) and at the severity the snippet itself
   supports — re-derived here with the deterministic heuristic classifier,
   because the evidence never changes between the heuristic and the agent.
   GPS to ``critical`` on coordinates alone is therefore impossible.
3. **No payload words in reproduction steps**: steps are defensive inspection
   of the *public* asset (``exiftool`` / ``pdfinfo`` / ``curl``). Steps
   containing attack tooling vocabulary are removed; if none survive, the
   finding falls back to the safe heuristic reproduction template.
4. **Evidence immutability** is structural: the output schema carries no
   ``finding_type`` / ``evidence_snippet`` fields, so there is nothing here to
   enforce beyond never copying model text back into those fields.
5. **Text↔severity coherence** (TASK-08): if ``justification`` explicitly
   cites a rubric level other than the assigned severity, the proposal is
   rejected and the graph falls back to the heuristic (the rubric wins).
"""

import logging
import re
from dataclasses import dataclass, field

from metatracer.classification.classifier import classify_heuristically
from metatracer.classification.rubric import SEVERITY_RANK, cap_severity, ceiling_for
from metatracer.classification.templates import (
    RenderContext,
    has_template,
    render_template,
    template_for,
    tool_for_content_type,
)
from metatracer.core.logging import sanitize_for_log
from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    Finding,
    FindingType,
    Severity,
)
from metatracer.detectors.base import collapse_whitespace
from metatracer.detectors.patterns import snippet_has_closed_secret

logger = logging.getLogger("metatracer.agents.guard")

# Attack-tooling and prompt-injection wording banned from model prose (TASK-29).
# Deliberately short; the spirit is defensive inspection, and an over-eager
# list would false-positive on legitimate prose.
_PAYLOAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmsfvenom\b", re.IGNORECASE),
    re.compile(r"\bmeterpreter\b", re.IGNORECASE),
    re.compile(r"\bmimikatz\b", re.IGNORECASE),
    re.compile(r"\bnc\s+-e\b", re.IGNORECASE),
    re.compile(r"\bbash\s+-i\b", re.IGNORECASE),
    re.compile(r"/etc/passwd", re.IGNORECASE),
    re.compile(r"\bcurl\b.{0,120}\|\s*(?:sh|bash)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\|\s*(?:sh|bash)\b", re.IGNORECASE),
    re.compile(r"\bignore\s+previous\b", re.IGNORECASE),
    re.compile(r"\bignore\s+all\s+instructions\b", re.IGNORECASE),
)

# Prose the model may rewrite. Over this length the field is truncated, not
# replaced; hostile wording is replaced by the heuristic template instead.
_MAX_PROSE_CHARS = 1500
_MAX_TITLE_CHARS = 120
_TITLE_MARK = "..."
_TITLE_LEAD = frozenset("#<`")


@dataclass(frozen=True, slots=True)
class GuardOutcome:
    """Guard-adjusted fields plus human-readable notes for the audit trail."""

    severity: Severity
    cited_evidence: str
    reproduction_steps: list[str]
    justification: str = ""
    impact_analysis: str = ""
    remediation: str = ""
    notes: list[str] = field(default_factory=list)
    rejected: bool = False


def transient_finding(payload: dict[str, str]) -> Finding:
    """Rebuild an in-memory Finding from a contract payload (never persisted).

    The heuristic classifier reads only ``finding_type``, ``field_source`` and
    ``evidence_snippet``; the remaining required fields are placeholders.
    """
    return Finding(
        run_id="guard",
        asset_id="guard",
        finding_type=FindingType(payload["finding_type"]),
        field_source=payload.get("field_source", ""),
        evidence_snippet=payload.get("evidence_snippet", ""),
        dedup_signature="guard",
        detector_method=DetectorMethod.rule,
        confidence=Confidence(payload.get("confidence", "low")),
    )


def _normalized(text: str) -> str:
    """Anchor-style normalization: collapse whitespace, then casefold."""
    return collapse_whitespace(text).casefold()


class EvidenceGuard:
    """Validates and repairs one model proposal against its own payload."""

    def check(
        self,
        *,
        severity: Severity,
        cited_evidence: str,
        reproduction_steps: list[str],
        payload: dict[str, str],
        justification: str = "",
        impact_analysis: str = "",
        remediation: str = "",
        baseline_severity: Severity | None = None,
    ) -> GuardOutcome:
        """Apply invariants 1-5; rejected proposals must not be persisted as-is."""
        notes: list[str] = []
        snippet = payload.get("evidence_snippet", "")
        finding_type = FindingType(payload["finding_type"])

        # --- Invariant 1: cited evidence must be a real substring. ---
        cited = cited_evidence.strip()
        if not cited or _normalized(cited) not in _normalized(snippet):
            notes.append(
                "cited_evidence was absent from the snippet (possible hallucination); "
                "replaced with the verbatim snippet and severity lowered one rank"
            )
            logger.warning(
                "evidence guard: hallucinated citation on %s finding: %s",
                sanitize_for_log(str(finding_type)),
                sanitize_for_log(cited_evidence),
            )
            cited = snippet
            severity = _one_rank_down(severity)

        # --- Invariant 2: ceilings and snippet-supported severity. ---
        capped = cap_severity(severity, ceiling_for(finding_type))
        if capped is not severity:
            notes.append(
                f"severity {severity} exceeds the {finding_type} ceiling; capped to {capped}"
            )
        severity = capped

        heuristic = classify_heuristically(transient_finding(payload)).severity
        if SEVERITY_RANK[severity] > SEVERITY_RANK[heuristic]:
            notes.append(
                f"severity {severity} not supported by the snippet; "
                f"lowered to the heuristic level {heuristic}"
            )
            severity = heuristic

        rejected = False
        if finding_type is FindingType.secret and not snippet_has_closed_secret(snippet):
            notes.append(
                "secret finding has no closed-allowlist pattern in the snippet; "
                "proposal rejected"
            )
            logger.warning(
                "evidence guard: rejected secret finding without an allowlist pattern"
            )
            severity = heuristic
            rejected = True

        # Operator feedback is applied when the finding was classified, so the
        # persisted baseline can be stricter than a fresh heuristic. The model
        # must not undo that correction (TASK-29).
        if (
            baseline_severity is not None
            and SEVERITY_RANK[severity] > SEVERITY_RANK[baseline_severity]
        ):
            notes.append(
                f"severity {severity} exceeds the operator-corrected baseline "
                f"{baseline_severity.value}; lowered to {baseline_severity.value}"
            )
            logger.warning(
                "evidence guard: lowered %s finding to operator baseline %s",
                sanitize_for_log(str(finding_type)),
                sanitize_for_log(baseline_severity.value),
            )
            severity = baseline_severity

        # --- Invariant 3: reproduction steps stay defensive. ---
        safe_steps = [step for step in reproduction_steps if not _has_payload_words(step)]
        if len(safe_steps) != len(reproduction_steps):
            removed = len(reproduction_steps) - len(safe_steps)
            notes.append(f"removed {removed} reproduction step(s) containing payload wording")
            logger.warning(
                "evidence guard: stripped %d payload-word reproduction step(s) on %s finding",
                removed,
                sanitize_for_log(str(finding_type)),
            )
        if not safe_steps:
            fallback = classify_heuristically(transient_finding(payload))
            safe_steps = list(fallback.reproduction_steps)
            notes.append("reproduction steps replaced by the defensive heuristic template")

        justification, impact_analysis, remediation = _repair_prose(
            payload,
            severity,
            justification=justification,
            impact_analysis=impact_analysis,
            remediation=remediation,
            notes=notes,
        )

        # --- Invariant 5: explanation must not cite a different rubric level. ---
        cited_levels = cited_rubric_levels(justification)
        if cited_levels and any(level is not severity for level in cited_levels):
            cited_labels = ", ".join(level.value for level in cited_levels)
            notes.append(
                f"explanation cites rubric level(s) {cited_labels} distinct from "
                f"assigned {severity.value}; proposal rejected"
            )
            logger.warning(
                "evidence guard: incoherent justification on %s finding "
                "(assigned %s, cited %s)",
                sanitize_for_log(str(finding_type)),
                sanitize_for_log(severity.value),
                sanitize_for_log(cited_labels),
            )
            return GuardOutcome(
                severity=severity,
                cited_evidence=cited,
                reproduction_steps=safe_steps,
                justification=justification,
                impact_analysis=impact_analysis,
                remediation=remediation,
                notes=notes,
                rejected=True,
            )

        return GuardOutcome(
            severity=severity,
            cited_evidence=cited,
            reproduction_steps=safe_steps,
            justification=justification,
            impact_analysis=impact_analysis,
            remediation=remediation,
            notes=notes,
            rejected=rejected,
        )

    def sanitize_title(self, title: str, payload: dict[str, str]) -> tuple[str, list[str]]:
        """One-line title, or the heuristic template when the draft is hostile."""
        notes: list[str] = []
        cleaned = _normalize_title(title)
        if not cleaned or _has_payload_words(cleaned):
            notes.append(
                "title contained disallowed wording; replaced by the heuristic template"
            )
            return fallback_title(payload), notes
        return cleaned, notes


_LEVEL_ALIASES: dict[str, Severity] = {
    "critical": Severity.critical,
    "high": Severity.high,
    "medium": Severity.medium,
    "low": Severity.low,
    "info": Severity.info,
    "informational": Severity.info,
}

# Matches "high-severity", "high severity", "severity: medium", "severity is high".
_CITED_LEVEL_RE = re.compile(
    r"(?:(?P<before>critical|high|medium|low|informational|info)\s*-?\s*severity"
    r"|severity\s*(?:is|:|of)?\s*(?P<after>critical|high|medium|low|informational|info))",
    re.IGNORECASE,
)


def cited_rubric_levels(text: str) -> set[Severity]:
    """Rubric levels the prose names explicitly; empty if it names none."""
    found: set[Severity] = set()
    for match in _CITED_LEVEL_RE.finditer(text or ""):
        token = (match.group("before") or match.group("after") or "").casefold()
        level = _LEVEL_ALIASES.get(token)
        if level is not None:
            found.add(level)
    return found


def _one_rank_down(severity: Severity) -> Severity:
    rank = SEVERITY_RANK[severity]
    if rank == 0:
        return severity
    for candidate, candidate_rank in SEVERITY_RANK.items():
        if candidate_rank == rank - 1:
            return candidate
    return severity  # pragma: no cover - the enum is closed


def _has_payload_words(step: str) -> bool:
    return any(pattern.search(step) for pattern in _PAYLOAD_PATTERNS)


_FALLBACK_TITLES: dict[FindingType, str] = {
    FindingType.gps: "Embedded GPS coordinates",
    FindingType.email: "Corporate email address",
    FindingType.internal_path: "Internal filesystem path",
    FindingType.software_version: "Software version disclosure",
    FindingType.debug_comment: "Debug or comment leftover",
    FindingType.internal_endpoint: "Internal endpoint",
    FindingType.cloud_storage: "Cloud storage reference",
    FindingType.secret: "Embedded credential",
}


def cap_to_baseline(severity: Severity, baseline: Severity | None) -> Severity:
    """Never let a fallback climb above the operator-corrected baseline."""
    if baseline is None or SEVERITY_RANK[severity] <= SEVERITY_RANK[baseline]:
        return severity
    return baseline


def has_hostile_wording(text: str) -> bool:
    """True when model prose contains payload or prompt-injection wording."""
    return _has_payload_words(text)


def fallback_title(payload: dict[str, str]) -> str:
    """Deterministic title: type and field, never the evidence text."""
    raw_type = payload.get("finding_type", "debug_comment")
    if raw_type in FindingType.__members__:
        finding_type = FindingType(raw_type)
    else:
        finding_type = FindingType.debug_comment
    field_source = payload.get("field_source", "").strip()
    label = _FALLBACK_TITLES[finding_type]
    return f"{label} in {field_source}" if field_source else label


def _normalize_title(title: str) -> str:
    """One line, no leading heading/HTML/code marker, length-capped."""
    text = " ".join(title.replace("\r", " ").replace("\n", " ").split())
    while text[:1] in _TITLE_LEAD:
        text = text[1:].lstrip()
    if len(text) > _MAX_TITLE_CHARS:
        text = text[: _MAX_TITLE_CHARS - len(_TITLE_MARK)] + _TITLE_MARK
    return text


def _cap_prose(text: str, notes: list[str], field_name: str) -> str:
    if len(text) <= _MAX_PROSE_CHARS:
        return text
    notes.append(f"{field_name} truncated to {_MAX_PROSE_CHARS} characters")
    return text[: _MAX_PROSE_CHARS - len(_TITLE_MARK)] + _TITLE_MARK


def _template_fields(payload: dict[str, str], severity: Severity) -> tuple[str, str, str]:
    """Heuristic justification, impact and remediation for the assigned severity."""
    finding_type = FindingType(payload["finding_type"])
    if not has_template(finding_type, severity):
        assessment = classify_heuristically(transient_finding(payload))
        return (
            assessment.justification,
            assessment.impact_analysis,
            assessment.remediation_advice,
        )
    rendered = render_template(
        template_for(finding_type, severity),
        RenderContext(
            snippet=payload.get("evidence_snippet", ""),
            field_source=payload.get("field_source", ""),
            finding_type=finding_type.value,
            asset_url=payload.get("asset_url") or "its published URL",
            tool=tool_for_content_type(
                payload.get("asset_content_type"),
                field_source=payload.get("field_source", ""),
            ),
        ),
    )
    remediation = "\n".join(
        f"{index}. {step}" for index, step in enumerate(rendered.remediation, start=1)
    )
    return rendered.justification, rendered.impact, remediation


def _repair_prose(
    payload: dict[str, str],
    severity: Severity,
    *,
    justification: str,
    impact_analysis: str,
    remediation: str,
    notes: list[str],
) -> tuple[str, str, str]:
    """Replace a hostile field with the heuristic template; never drop the finding."""
    template_justification, template_impact, template_remediation = _template_fields(
        payload, severity
    )
    fields = {
        "justification": (justification, template_justification),
        "impact_analysis": (impact_analysis, template_impact),
        "remediation": (remediation, template_remediation),
    }
    repaired: dict[str, str] = {}
    for name, (original, template) in fields.items():
        text = _cap_prose(original, notes, name)
        if text and _has_payload_words(text):
            notes.append(
                f"{name} contained disallowed wording; replaced by the heuristic template"
            )
            logger.warning(
                "evidence guard: replaced %s on %s finding with the heuristic template",
                name,
                sanitize_for_log(payload.get("finding_type", "")),
            )
            repaired[name] = template
        else:
            repaired[name] = text
    return repaired["justification"], repaired["impact_analysis"], repaired["remediation"]
