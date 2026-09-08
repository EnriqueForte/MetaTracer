"""HeuristicRiskClassifier (TASK-03 subtask 3.3).

Deterministic, offline severity baseline: no I/O, no network, no OSINT, no
geocoding, no CVE lookups. Same inputs always produce the same output. The
classifier reads the finding's own evidence (snippet, type, field_source) and
optionally the asset (URL and content type, used only to phrase reproduction
steps); it never opens files.

Pipeline position: detectors (TASK-02, severity NULL) -> this heuristic
(baseline severity + templates) -> agent (TASK-05, may adjust severity within
the rubric and rewrite prose; the guard may only lower or reject). When the
agent never runs, these templates are the report content verbatim.

Anti-hallucination anchoring (subtask 3.2): empty evidence or evidence that
does not match the expected shape for its type is forced to ``info``; on
ambiguity the level goes down, never up; per-type ceilings come from
:mod:`metatracer.classification.rubric`. The full substring anchor against
``RawMetadataItem`` rows lives in :mod:`metatracer.classification.anchor` and
is applied by the pipeline, which needs database access this layer avoids.
"""

import json
import re
from dataclasses import dataclass

from metatracer.classification.anchor import parse_gps_line
from metatracer.classification.rubric import cap_severity, ceiling_for
from metatracer.classification.templates import (
    UNANCHORED_EVIDENCE,
    RenderContext,
    SeverityTemplate,
    render_template,
    template_for,
    tool_for_content_type,
)
from metatracer.db.models import Asset, Finding, FindingType, Severity

# Secret markers that push a debug comment to critical (subtask 3.2.3,
# verbatim from the task contract).
_SECRET_RE = re.compile(r"\b(?:password|secret|api[_-]?key|token|credential)s?\b", re.IGNORECASE)

# Debug keyword patterns mirrored from detectors/debug.py — keep in sync: the
# detector anchors on them, the classifier maps them to severity bands.
_STRONG_RES = (
    re.compile(r"\b(?:TODO|FIXME|DEBUG|XXX|HACK)\s*:", re.IGNORECASE),
    re.compile(r"\bNOT\s+FOR\s+PUBLIC\s+RELEASE\b", re.IGNORECASE),
    re.compile(r"\bJIRA-\d+\b", re.IGNORECASE),
    re.compile(r"\bGL-\d+\b", re.IGNORECASE),
    re.compile(r"#ISSUE-\d+\b", re.IGNORECASE),
)
_WEAK_RE = re.compile(r"\b(?:CONFIDENTIAL|INTERNAL|DRAFT|TEST)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")

_EMAIL_SHAPE_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Role mailboxes: published contact channels, not personal leaks -> low.
_GENERIC_MAILBOXES = frozenset(
    {
        "info",
        "contact",
        "hello",
        "support",
        "sales",
        "marketing",
        "office",
        "mail",
        "email",
        "webmaster",
        "noreply",
        "no-reply",
        "press",
        "hr",
        "jobs",
        "careers",
        "team",
    }
)

_WINDOWS_USER_RE = re.compile(
    r"^[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/]+", re.IGNORECASE
)
_WINDOWS_SYSTEM_RE = re.compile(r"^[A-Za-z]:[\\/](?:Windows|inetpub|xampp)[\\/]", re.IGNORECASE)
_UNC_RE = re.compile(r"^\\\\[^\\]+")
# /var/www/<seg> with a generic deploy segment names no user (rubric medium
# example: /var/www/intranet); any other segment is treated as user-ish.
_GENERIC_WWW_SEGMENTS = frozenset(
    {
        "html",
        "htdocs",
        "www",
        "public",
        "intranet",
        "extranet",
        "web",
        "webroot",
        "site",
        "sites",
        "app",
        "apps",
        "blog",
        "shop",
        "static",
    }
)
_HIGH_UNIX_PREFIXES = ("/home/", "/users/", "/root/")
_MEDIUM_UNIX_PREFIXES = ("/private/var/", "/srv/")


@dataclass(frozen=True, slots=True)
class SeverityAssessment:
    """Classifier output; strings are ready to persist on the Finding.

    ``remediation_advice`` is a numbered, newline-separated list;
    ``reproduction_steps`` is serialized to a JSON array by
    :func:`apply_assessment` (the JSON exporter materializes it as a list).
    """

    severity: Severity
    justification: str
    impact_analysis: str
    remediation_advice: str
    reproduction_steps: tuple[str, ...]


class HeuristicRiskClassifier:
    """Maps a finding to a rubric-anchored severity with template prose."""

    def classify(self, finding: Finding, asset: Asset | None = None) -> SeverityAssessment:
        """Classify one finding; pure function of the persisted fields."""
        snippet = finding.evidence_snippet
        if not snippet or not snippet.strip():
            return self._assess(finding, asset, Severity.info, template=UNANCHORED_EVIDENCE)
        severity = self._severity_for(finding)
        # Belt and braces: the per-type logic already respects the ceilings,
        # but the rubric invariant is enforced centrally (subtask 3.2.3).
        severity = cap_severity(severity, ceiling_for(finding.finding_type))
        return self._assess(finding, asset, severity)

    def _severity_for(self, finding: Finding) -> Severity:
        snippet = finding.evidence_snippet.strip()
        match finding.finding_type:
            case FindingType.gps:
                return self._gps_severity(snippet)
            case FindingType.email:
                return self._email_severity(snippet)
            case FindingType.internal_path:
                return self._path_severity(snippet)
            case FindingType.software_version:
                return self._software_severity(snippet)
            case FindingType.debug_comment:
                return self._debug_severity(snippet)
        return Severity.info  # pragma: no cover - the enum is closed

    @staticmethod
    def _gps_severity(snippet: str) -> Severity:
        # Valid coordinates alone are high; the ceiling forbids critical
        # without text identifying a home/person/facility (no geocoding).
        return Severity.high if parse_gps_line(snippet) is not None else Severity.info

    @staticmethod
    def _email_severity(snippet: str) -> Severity:
        if _EMAIL_SHAPE_RE.match(snippet) is None:
            return Severity.info  # does not match the type shape
        local = snippet.partition("@")[0].lower()
        return Severity.low if local in _GENERIC_MAILBOXES else Severity.medium

    @staticmethod
    def _path_severity(snippet: str) -> Severity:
        if _UNC_RE.match(snippet) or _WINDOWS_USER_RE.match(snippet):
            return Severity.high  # username or internal host/share
        if _WINDOWS_SYSTEM_RE.match(snippet):
            return Severity.medium  # system root without a user
        low = snippet.lower()
        if low.startswith(_HIGH_UNIX_PREFIXES):
            return Severity.high  # /home/<user>, /Users/<user>, /root
        if low.startswith("/var/www"):
            rest = snippet[len("/var/www") :].lstrip("/")
            if not rest:
                return Severity.medium
            segment = rest.split("/", 1)[0].lower()
            return Severity.medium if segment in _GENERIC_WWW_SEGMENTS else Severity.high
        if low.startswith(_MEDIUM_UNIX_PREFIXES):
            return Severity.medium
        return Severity.info  # not a recognized internal-path shape

    @staticmethod
    def _software_severity(snippet: str) -> Severity:
        # A version-less producer is not a finding; if one slips through, the
        # evidence does not match the type shape -> info. Ceiling: low.
        return Severity.low if re.search(r"\d", snippet) else Severity.info

    @staticmethod
    def _debug_severity(snippet: str) -> Severity:
        if _SECRET_RE.search(snippet):
            return Severity.critical
        if any(pattern.search(snippet) for pattern in _STRONG_RES):
            return Severity.medium
        if _WEAK_RE.search(snippet):
            # Isolated marker ("DRAFT" alone) -> info; marker plus surrounding
            # prose -> low (ambiguity rule: one level down, never up).
            content_words = [
                word for word in _WORD_RE.findall(snippet.lower()) if not _WEAK_RE.fullmatch(word)
            ]
            return Severity.low if content_words else Severity.info
        return Severity.info  # no recognized marker: ambiguous evidence

    def _assess(
        self,
        finding: Finding,
        asset: Asset | None,
        severity: Severity,
        template: SeverityTemplate | None = None,
    ) -> SeverityAssessment:
        if template is None:
            template = template_for(finding.finding_type, severity)
        rendered = render_template(template, _context_for(finding, asset))
        remediation = "\n".join(
            f"{index}. {step}" for index, step in enumerate(rendered.remediation, start=1)
        )
        return SeverityAssessment(
            severity=severity,
            justification=rendered.justification,
            impact_analysis=rendered.impact,
            remediation_advice=remediation,
            reproduction_steps=rendered.reproduction,
        )


def _context_for(finding: Finding, asset: Asset | None) -> RenderContext:
    return RenderContext(
        snippet=finding.evidence_snippet,
        field_source=finding.field_source,
        finding_type=str(finding.finding_type),
        asset_url=asset.final_url if asset is not None else "its published URL",
        tool=tool_for_content_type(
            asset.content_type if asset is not None else None,
            field_source=finding.field_source,
        ),
    )


def classify_heuristically(finding: Finding, asset: Asset | None = None) -> SeverityAssessment:
    """Contracted entry point (subtask 3.3); the classifier is stateless."""
    return HeuristicRiskClassifier().classify(finding, asset)


def unanchored_assessment(finding: Finding, asset: Asset | None = None) -> SeverityAssessment:
    """Forced ``info`` assessment when evidence fails the anchor check (3.2.1)."""
    return HeuristicRiskClassifier()._assess(
        finding, asset, Severity.info, template=UNANCHORED_EVIDENCE
    )


def apply_assessment(finding: Finding, assessment: SeverityAssessment) -> Finding:
    """Write severity + template prose onto the Finding (subtask 3.3.3).

    ``agent_model_used`` stays untouched (empty here; TASK-05 sets it, or
    ``heuristic-fallback`` when the agent fails). ``finding_type`` and
    ``evidence_snippet`` are evidence and are never modified.
    """
    finding.severity = assessment.severity
    finding.severity_justification = assessment.justification
    finding.impact_analysis = assessment.impact_analysis
    finding.remediation_advice = assessment.remediation_advice
    finding.reproduction_steps = json.dumps(list(assessment.reproduction_steps), ensure_ascii=False)
    return finding
