"""DebugCommentDetector (TASK-02 subtask 2.5).

Scans free-text fields (Comment, UserComment, Description, Subject, Keywords,
``xmp:Note``, ImageDescription — matched by local name) for leftover
development chatter.

Strong keywords (``high`` confidence): ``TODO:``, ``FIXME:``, ``DEBUG:``,
``XXX:``, ``HACK:``, ``NOT FOR PUBLIC RELEASE`` and ticket references
(``JIRA-123``, ``GL-42``, ``#ISSUE-7``). Weak keywords (``medium``):
``CONFIDENTIAL``, ``INTERNAL``, ``DRAFT``, ``TEST`` with no development
context — the TASK-03 classifier may still lower them to ``low``/``info``.

Weak keywords only fire in SHORT fields (``_WEAK_MAX_CHARS``): real debug
leftovers are terse fragments (``DRAFT``, ``INTERNAL - do not share``), while
long prose (public captions, abstracts) needs a strong keyword. Rationale:
the Phase-0 validation against NASA's public image library found ``TEST``
firing on the caption "Artemis II test flight" in ``xmp:dc:description`` —
a false-positive class on any descriptive prose.

One finding per field, not per keyword: the anchor is the first strong match,
or the first weak one when no strong keyword is present. The snippet is a
~150-char whitespace-collapsed window around the anchor.
"""

import re
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import (
    FindingDraft,
    collapse_whitespace,
    normalize_text,
    snippet_around,
)
from metatracer.detectors.patterns import STRONG_DEBUG_RES, WEAK_DEBUG_RE

# Local key names (part after the last ":") holding free text. Both singular
# and plural of Comment: the task lists "Comment" and real PDFs use both.
_DEBUG_KEYS = frozenset(
    {
        "comment",
        "comments",
        "usercomment",
        "description",
        "subject",
        "keywords",
        "note",
        "imagedescription",
    }
)

_STRONG_RES = STRONG_DEBUG_RES
_WEAK_RE = WEAK_DEBUG_RE

# Maximum field length for a weak keyword to anchor a finding. Longer text is
# prose (captions, abstracts) where a bare weak keyword is noise; strong
# keywords remain unambiguous at any length.
_WEAK_MAX_CHARS = 100


class DebugCommentDetector:
    """Detects debug/development leftovers in free-text metadata fields."""

    finding_type = FindingType.debug_comment

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            local = item.key.rpartition(":")[2].lower()
            if local not in _DEBUG_KEYS:
                continue
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            hit = _first_strong(text)
            if hit is None and len(text) <= _WEAK_MAX_CHARS:
                hit = _first_weak(text)
            match, confidence = hit or (None, None)
            if match is None or confidence is None:
                continue
            drafts.append(
                FindingDraft(
                    finding_type=FindingType.debug_comment,
                    field_source=f"{item.namespace}:{item.key}",
                    evidence_snippet=snippet_around(text, match.start(), match.end()),
                    confidence=confidence,
                )
            )
        return drafts


def _first_strong(text: str) -> tuple[re.Match[str], Confidence] | None:
    for pattern in _STRONG_RES:
        match = pattern.search(text)
        if match is not None:
            return match, Confidence.high
    return None


def _first_weak(text: str) -> tuple[re.Match[str], Confidence] | None:
    match = _WEAK_RE.search(text)
    return (match, Confidence.medium) if match is not None else None
