"""Detector contract and shared text helpers (TASK-02 subtask 2.0).

Detectors read only structured ``RawMetadataItem`` rows — opening the original
file is forbidden — and emit :class:`FindingDraft` objects with ``severity``
left NULL: classification is TASK-03/TASK-05, never this stage. Every value is
NFC-normalized and stripped before matching, and evidence snippets are capped
at ~150 chars (GPS excepted: one coordinate line).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from metatracer.db.models import Confidence, DetectorMethod, FindingType, RawMetadataItem

MAX_SNIPPET_CHARS = 150
_SNIPPET_MARK = "..."
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FindingDraft:
    """Detector output before consolidation and persistence.

    There is no ``severity`` here by contract: detectors never classify.
    ``detector_method`` is always ``rule`` for this deterministic stage.
    """

    finding_type: FindingType
    field_source: str
    evidence_snippet: str
    confidence: Confidence
    detector_method: DetectorMethod = field(default=DetectorMethod.rule)


class Detector(Protocol):
    """A deterministic detector over the metadata items of one asset."""

    finding_type: FindingType

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]: ...


def normalize_text(value: str) -> str:
    """NFC + strip; applied to every metadata value before matching."""
    return unicodedata.normalize("NFC", value).strip()


def collapse_whitespace(text: str) -> str:
    """Fold every whitespace run into a single space (single-line evidence)."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def snippet(text: str, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    """Cap ``text`` at ~max_chars, marking the cut."""
    text = collapse_whitespace(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(_SNIPPET_MARK)] + _SNIPPET_MARK


def snippet_around(text: str, start: int, end: int, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    """Window of up to ~max_chars of ``text`` centered on the ``[start, end)`` match.

    Offsets refer to ``text`` as given (collapse whitespace first so match
    offsets stay valid). Clipped sides are marked with ``...``.
    """
    if len(text) <= max_chars:
        return text
    inner = max_chars - 2 * len(_SNIPPET_MARK)  # worst case: both sides clipped
    begin = max(0, (start + end) // 2 - inner // 2)
    stop = min(len(text), begin + inner)
    begin = max(0, stop - inner)
    prefix = _SNIPPET_MARK if begin > 0 else ""
    suffix = _SNIPPET_MARK if stop < len(text) else ""
    return f"{prefix}{text[begin:stop]}{suffix}"
