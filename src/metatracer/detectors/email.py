"""EmailDetector (TASK-02 subtask 2.2).

Practical regex (not full RFC 5322) over every value of the asset — scanning
all fields is cheap and avoids false negatives beyond the classic
Author/Creator/Producer set. Domains of the tools that *produce* documents
(Adobe, Apple, Microsoft...) are blacklisted: ``support@adobe.com`` is vendor
noise, not a target leak. The domain comparison is lowercase and covers
subdomains (``mail.adobe.com`` is still Adobe).

The snippet is the exact email, never the whole paragraph. Confidence is
``high`` when the field value is essentially the email (allowing surrounding
brackets/quotes) and ``medium`` when it is embedded in longer prose.
"""

import re
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, collapse_whitespace, normalize_text

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Domains of document-tooling vendors and placeholders: never a target leak.
TOOL_DOMAIN_BLACKLIST = frozenset(
    {
        "adobe.com",
        "apple.com",
        "microsoft.com",
        "w3.org",
        "xml.org",
        "example.com",
        "localhost",
        "example.org",
        # Open-source ecosystems: authors, registries and CDNs whose emails
        # are attribution, never a target leak (issue @ gitlab-shell run).
        "github.com",
        "githubusercontent.com",
        "gitlab.com",  # meta-domain of the scanning target itself
        "jsdelivr.com",
        "cdnjs.com",
        "unpkg.com",
        "npmjs.com",
        "rubaxa.org",  # Sortable/Vue.Draggable author
        "feross.org",  # ieee754/buffer author
        "snowplowanalytics.com",
        "vuejs.org",
        "cloudflare.com",
    }
)

# Attribution markers that cancel an email: license/credit lines in bundles
# and documents quote third-party authors whose email is not a leak of the
# audited asset. The marker must be on the *line* that contains the email
# (``collapse_whitespace`` keeps newlines only at the start/end, so the raw
# line check uses a per-line split before collapsing).
_ATTRIBUTION_LINE_RE = re.compile(
    r"\b(?:author|authors?|license|licence|copyright|©|\(c\)|\(C\)|"
    r"maintainer|contributors?|credits?|<https?://)",
    re.IGNORECASE,
)

# When the marker is a bare domain-in-brackets (``<feross.org>``, ``<https://…>``)
# it appears at the *token boundary* just before the email, not inside it.
_ATTRIBUTION_BRACKET_EMAIL_RE = re.compile(r"<https?://[^>\s]+>", re.IGNORECASE)

# Wrappers tolerated around a "bare" email: <jane@x.com>, "jane@x.com", ...
_WRAPPER_CHARS = "<>()[]{}\"' "


class EmailDetector:
    """Detects email addresses in any metadata field of the asset."""

    finding_type = FindingType.email

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            # Per-line attribution context, checked before collapsing newlines
            # so a license header cannot cancel a real leak in later prose.
            lines = normalize_text(item.value).splitlines()
            seen_in_field: set[str] = set()
            for match in EMAIL_RE.finditer(text):
                email = match.group(0)
                domain = email.rpartition("@")[2].lower()
                if _is_tool_domain(domain) or email.lower() in seen_in_field:
                    continue
                if _is_attribution_line(lines, email):
                    continue
                seen_in_field.add(email.lower())
                confidence = (
                    Confidence.high if text.strip(_WRAPPER_CHARS) == email else Confidence.medium
                )
                drafts.append(
                    FindingDraft(
                        finding_type=FindingType.email,
                        field_source=f"{item.namespace}:{item.key}",
                        evidence_snippet=email,
                        confidence=confidence,
                    )
                )
        return drafts


def _is_tool_domain(domain: str) -> bool:
    """Exact blacklist hit or a subdomain of a blacklisted domain."""
    return any(
        domain == blocked or domain.endswith(f".{blocked}") for blocked in TOOL_DOMAIN_BLACKLIST
    )


def _is_attribution_line(lines: list[str], email: str) -> bool:
    """True when the email sits in a license/credit/attribution line.

    JS bundles and library docs carry ``@author <dev@example.org>``,
    ``@license MIT``, ``(c) 2022 Company <dev@example.org>`` or a bare
    ``<https://…>`` credit; those emails identify a *third-party author*, not a
    leak of the audited asset. Markers are matched on the raw line (before
    whitespace collapsing) so ``@author`` next to the email is recognised.
    """
    needle = email.lower()
    for raw_line in lines:
        line = collapse_whitespace(normalize_text(raw_line)).lower()
        if needle not in line:
            continue
        # License/credit markers, or a bracketed URL on the same line.
        if _ATTRIBUTION_LINE_RE.search(line) or _ATTRIBUTION_BRACKET_EMAIL_RE.search(line):
            return True
    return False
