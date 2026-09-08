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
    }
)

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
            seen_in_field: set[str] = set()
            for match in EMAIL_RE.finditer(text):
                email = match.group(0)
                domain = email.rpartition("@")[2].lower()
                if _is_tool_domain(domain) or email.lower() in seen_in_field:
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
