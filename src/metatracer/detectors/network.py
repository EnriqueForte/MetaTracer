"""Internal endpoints and cloud-storage URLs found in metadata (Fase 3).

Both detectors read stored text only. A cloud URL is recorded and never
requested: checking whether the bucket is public is the analyst's decision.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, collapse_whitespace, normalize_text, snippet

_WRAPPER = "<>()[]{}\"' "

_IPV4_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)"
)
_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9-@])("
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:svc\.cluster\.local|internal|corp|local|lan)"
    r")(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
# The label before ``s3`` must be a real boundary so ``nots3.amazonaws.com``
# is not a bucket host.
_CLOUD_RES = (
    re.compile(
        r"(?<![A-Za-z0-9])((?:https?://)?(?:[A-Za-z0-9][A-Za-z0-9.-]*\.)?"
        r"s3(?:\.[A-Za-z0-9-]+)?\.amazonaws\.com(?:/[^\s\"'<>]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9])((?:https?://)?(?:[A-Za-z0-9][A-Za-z0-9.-]*\.)?"
        r"storage\.googleapis\.com(?:/[^\s\"'<>]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9])((?:https?://)?[A-Za-z0-9][A-Za-z0-9.-]*"
        r"\.blob\.core\.windows\.net(?:/[^\s\"'<>]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9])((?:https?://)?[A-Za-z0-9][A-Za-z0-9.-]*"
        r"\.r2\.cloudflarestorage\.com(?:/[^\s\"'<>]*)?)",
        re.IGNORECASE,
    ),
)


class InternalEndpointDetector:
    """RFC1918 addresses and internal hostnames in any metadata field."""

    finding_type = FindingType.internal_endpoint

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            seen: set[str] = set()
            for raw in _endpoint_matches(text):
                token = raw.casefold().rstrip(".")
                if token in seen:
                    continue
                seen.add(token)
                drafts.append(_draft(item, FindingType.internal_endpoint, token, text))
        return drafts


class CloudStorageDetector:
    """Storage URLs in metadata. The URL is evidence; it is not fetched."""

    finding_type = FindingType.cloud_storage

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            seen: set[str] = set()
            for match in _cloud_matches(text):
                token = _without_query(match).rstrip(".,);")
                key = token.casefold()
                if not token or key in seen:
                    continue
                seen.add(key)
                drafts.append(_draft(item, FindingType.cloud_storage, snippet(token), text))
        return drafts


def _draft(
    item: RawMetadataItem, finding_type: FindingType, evidence: str, field_text: str
) -> FindingDraft:
    bare = field_text.strip(_WRAPPER)
    confidence = Confidence.high if bare.casefold() == evidence.casefold() else Confidence.medium
    return FindingDraft(
        finding_type=finding_type,
        field_source=f"{item.namespace}:{item.key}",
        evidence_snippet=evidence,
        confidence=confidence,
    )


def _endpoint_matches(text: str) -> list[str]:
    found: list[str] = []
    for match in _IPV4_RE.finditer(text):
        candidate = match.group(1)
        if _is_rfc1918(candidate):
            found.append(candidate)
    hosts = [match.group(1) for match in _HOST_RE.finditer(text)]
    hosts.sort(key=len, reverse=True)
    kept: list[str] = []
    for host in hosts:
        folded = host.casefold()
        if any(folded in longer.casefold() and folded != longer.casefold() for longer in kept):
            continue
        kept.append(host)
    found.extend(kept)
    return found


def _is_rfc1918(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return False
    if any(number > 255 for number in numbers):
        return False
    first, second = numbers[0], numbers[1]
    if first == 10:
        return True
    if first == 192 and second == 168:
        return True
    return first == 172 and 16 <= second <= 31


def _cloud_matches(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _CLOUD_RES:
        found.extend(match.group(1) for match in pattern.finditer(text))
    return found


def _without_query(token: str) -> str:
    """Drop the query and fragment. A presigned URL's signature is not evidence."""
    return token.split("?", 1)[0].split("#", 1)[0]
