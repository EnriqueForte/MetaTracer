"""Fixed English prose templates per finding type + severity (TASK-03, 3.3.2).

These templates are the report content when TASK-05 does not run; the agent
may later rewrite the prose (never the evidence). Every entry provides one
impact sentence and 1-3 remediation steps. Reproduction is deliberately
non-exploitative: inspect the *public* file with ``exiftool`` / ``pdfinfo``.

Placeholders rendered by :func:`render_template`:

- ``{snippet}``       evidence snippet (verbatim, never rewritten)
- ``{field_source}``  metadata field(s) the evidence came from
- ``{finding_type}``  contract value (e.g. ``internal_path``)
- ``{asset_url}``     public URL of the asset, or a generic phrase
- ``{tool}``          ``pdfinfo`` for PDFs, ``curl`` for HTML/JS/headers, else ``exiftool``
"""

from dataclasses import dataclass

from metatracer.db.models import FindingType, Severity


@dataclass(frozen=True, slots=True)
class SeverityTemplate:
    """Prose skeleton for one (finding_type, severity) pair."""

    justification: str
    impact: str
    remediation: tuple[str, ...]
    reproduction: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Values interpolated into templates; derived only from persisted data."""

    snippet: str
    field_source: str
    finding_type: str
    asset_url: str
    tool: str


def tool_for_content_type(content_type: str | None, field_source: str = "") -> str:
    """Inspection tool named in reproduction steps.

    PDF → ``pdfinfo``. HTML / JS / HTTP-header evidence → ``curl``.
    Everything else → ``exiftool``.
    """
    source = field_source.strip().lower()
    if source.startswith(("http:", "html:", "js:")):
        return "curl"
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct == "application/pdf":
        return "pdfinfo"
    if ct in {
        "text/html",
        "application/xhtml+xml",
        "application/javascript",
        "text/javascript",
        "application/ecmascript",
        "text/ecmascript",
    }:
        return "curl"
    return "exiftool"


def render_template(template: SeverityTemplate, context: RenderContext) -> SeverityTemplate:
    """Interpolate placeholders; the snippet itself is inserted verbatim."""

    def fmt(text: str) -> str:
        return text.format(
            snippet=context.snippet,
            field_source=context.field_source,
            finding_type=context.finding_type,
            asset_url=context.asset_url,
            tool=context.tool,
        )

    return SeverityTemplate(
        justification=fmt(template.justification),
        impact=fmt(template.impact),
        remediation=tuple(fmt(step) for step in template.remediation),
        reproduction=tuple(fmt(step) for step in template.reproduction),
    )


_INSPECT_STEPS = (
    "Fetch the public asset ({asset_url}) and save it locally.",
    "Run `{tool}` on the file and inspect {field_source}.",
    "Confirm the metadata matches the reported snippet.",
)

_TEMPLATES: dict[tuple[FindingType, Severity], SeverityTemplate] = {
    # --- gps: valid coordinates are always high in the heuristic (ceiling) ---
    (FindingType.gps, Severity.high): SeverityTemplate(
        justification=(
            "The asset embeds precise GPS coordinates ({snippet}) in {field_source}; "
            "a valid coordinate pair is high-impact location evidence on its own."
        ),
        impact=(
            "Precise location metadata can reveal where the material was produced, "
            "enabling physical or social-engineering reconnaissance against people "
            "or facilities."
        ),
        remediation=(
            "Strip location tags before publication (e.g. `exiftool -gps:all= file`).",
            "Disable geotagging on devices used to produce public material.",
            "Re-publish the asset and verify the GPS fields are gone.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    # --- email ---
    (FindingType.email, Severity.medium): SeverityTemplate(
        justification=(
            "Personal corporate address '{snippet}' exposed in {field_source} reveals "
            "the target's email naming convention."
        ),
        impact=(
            "A valid employee address enables targeted phishing, credential attacks "
            "against corporate SSO and employee enumeration."
        ),
        remediation=(
            "Remove personal addresses from the metadata of published documents.",
            "Prefer role-based addresses in public material.",
            "Add a metadata scrubbing step to the publication pipeline.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    (FindingType.email, Severity.low): SeverityTemplate(
        justification=(
            "Generic role address '{snippet}' in {field_source}; widely published "
            "mailboxes carry limited intelligence value."
        ),
        impact=(
            "A role address confirms a contact channel but reveals little about "
            "individuals or internal structure."
        ),
        remediation=("Remove addresses from the metadata of published documents.",),
        reproduction=_INSPECT_STEPS,
    ),
    # --- internal_path ---
    (FindingType.internal_path, Severity.high): SeverityTemplate(
        justification=(
            "Internal path '{snippet}' in {field_source} exposes a username or an "
            "internal host/share name together with directory layout."
        ),
        impact=(
            "Usernames and internal shares feed password spraying, spear phishing "
            "and lateral-movement reconnaissance."
        ),
        remediation=(
            "Scrub filesystem paths from metadata before publication.",
            "Avoid exporting documents directly from user profile directories.",
            "Add metadata linting to the release pipeline.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    (FindingType.internal_path, Severity.medium): SeverityTemplate(
        justification=(
            "Deploy/system path '{snippet}' in {field_source} reveals server layout "
            "without identifying a user."
        ),
        impact=(
            "Directory conventions help an attacker map the environment and "
            "prioritize further reconnaissance."
        ),
        remediation=("Scrub filesystem paths from metadata before publication.",),
        reproduction=_INSPECT_STEPS,
    ),
    # --- software_version: always low (ceiling) ---
    (FindingType.software_version, Severity.low): SeverityTemplate(
        justification=(
            "Producer string '{snippet}' in {field_source} discloses a software name and version."
        ),
        impact=(
            "Version disclosure helps an attacker fingerprint the stack and "
            "prioritize known-vulnerability research; this evidence alone implies "
            "no specific vulnerability."
        ),
        remediation=(
            "Remove or genericize Producer/CreatorTool fields in published files.",
            "Keep the disclosed software patched as general hygiene.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    # --- debug_comment ---
    (FindingType.debug_comment, Severity.critical): SeverityTemplate(
        justification=(
            "Debug comment in {field_source} contains a secret/credential marker: '{snippet}'."
        ),
        impact=(
            "If the referenced secret is valid, this is direct credential exposure "
            "and may allow unauthorized access to internal systems."
        ),
        remediation=(
            "Remove the comment from the published asset immediately.",
            "Rotate any credential referenced by the comment.",
            "Audit the publication pipeline to strip free-text comment fields.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    (FindingType.debug_comment, Severity.medium): SeverityTemplate(
        justification=(
            "Development leftover in {field_source} ('{snippet}') exposes internal "
            "process or project-tracking context."
        ),
        impact=(
            "Internal tickets, TODOs and staging references aid social engineering "
            "and reveal unfinished or sensitive work."
        ),
        remediation=(
            "Strip comment/description fields before publication.",
            "Add metadata linting to the release pipeline.",
        ),
        reproduction=_INSPECT_STEPS,
    ),
    (FindingType.debug_comment, Severity.low): SeverityTemplate(
        justification=(
            "Generic marker in {field_source} ('{snippet}') appears with surrounding "
            "context; limited sensitivity on its own."
        ),
        impact="Indicates document hygiene issues with minor reconnaissance value.",
        remediation=("Strip comment/description fields before publication.",),
        reproduction=_INSPECT_STEPS,
    ),
    (FindingType.debug_comment, Severity.info): SeverityTemplate(
        justification=(
            "Isolated generic marker in {field_source} ('{snippet}') with no actionable context."
        ),
        impact="No direct impact identified from the available evidence.",
        remediation=("Strip comment/description fields before publication.",),
        reproduction=_INSPECT_STEPS,
    ),
}

# Generic info-level templates (subtask 3.2.1 / 3.2.2): empty or unanchored
# evidence, and evidence that does not match the expected shape for its type.
UNANCHORED_EVIDENCE = SeverityTemplate(
    justification=(
        "The evidence snippet is empty or could not be re-anchored to the metadata "
        "extracted from the asset; the anti-hallucination rule forces info."
    ),
    impact="No impact can be derived from missing or unverifiable evidence.",
    remediation=("Review the source field manually if it matters to the engagement.",),
    reproduction=(
        "Fetch the public asset ({asset_url}) and save it locally.",
        "Run `{tool}` on the file and review the raw metadata fields.",
    ),
)

AMBIGUOUS_EVIDENCE = SeverityTemplate(
    justification=(
        "The evidence '{snippet}' is empty, generic or does not match the expected "
        "shape for {finding_type}; downgraded to info per the rubric."
    ),
    impact="No direct impact identified from the available evidence.",
    remediation=("Review the source field manually if it matters to the engagement.",),
    reproduction=(
        "Fetch the public asset ({asset_url}) and save it locally.",
        "Run `{tool}` on the file and review the raw metadata fields.",
    ),
)


def template_for(finding_type: FindingType, severity: Severity) -> SeverityTemplate:
    """Template for a type+level pair; info falls back to the generic template."""
    if severity is Severity.info:
        return _TEMPLATES.get((finding_type, severity), AMBIGUOUS_EVIDENCE)
    return _TEMPLATES[(finding_type, severity)]


def has_template(finding_type: FindingType, severity: Severity) -> bool:
    """True when a type renders that severity without fabricating prose.

    ``info`` always renders (the generic ambiguous-evidence template); other
    levels require a real template for the type, otherwise the report would
    KeyError. Used by the feedback injection (TASK-13) to ensure a down-vote
    only lands on a severity the report can actually write.
    """
    if severity is Severity.info:
        return True
    return (finding_type, severity) in _TEMPLATES
