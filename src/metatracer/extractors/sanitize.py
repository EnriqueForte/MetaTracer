"""Value hygiene for extractors: every persisted metadata value passes through here.

Contract (TASK-01 subtask 1.4.4 and the shared data contracts):

- output is always text, never bytes;
- tuples, rationals (Pillow ``IFDRational``) and bytes become short JSON or
  UTF-8 text (``errors="replace"``);
- values over ~2 KB are truncated with a ``[truncated]`` marker;
- binary blobs are never persisted: callers skip blob keys (ICC profile, EXIF
  thumbnail) up front, and :func:`sanitize_value` refuses oversized byte
  values as a second line of defense.
"""

import json
from datetime import date, datetime
from enum import Enum
from typing import Any

MAX_VALUE_CHARS = 2048
TRUNCATION_MARK = "[truncated]"
# Raw bytes longer than this are treated as blobs (ICC, thumbnails, MakerNote)
# and refused, even if the caller forgot to filter the key.
_MAX_BLOB_BYTES = 4096
_MAX_NESTING = 8


def truncate(text: str, max_chars: int = MAX_VALUE_CHARS) -> str:
    """Cut ``text`` to ``max_chars``, ending with the truncation marker."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def sanitize_value(value: Any, max_chars: int = MAX_VALUE_CHARS) -> str | None:
    """Convert an extractor value to persistable text.

    Returns ``None`` when the value is not representable as short text (a
    binary blob or an empty container) — the caller then omits the field.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return truncate(value.replace("\x00", ""), max_chars)
    normalized = _normalize(value, depth=0)
    if normalized is None:
        return None
    if isinstance(normalized, str):
        return truncate(normalized.replace("\x00", ""), max_chars)
    return truncate(json.dumps(normalized, ensure_ascii=False), max_chars)


def _normalize(value: Any, depth: int) -> Any:
    """Reduce exotic extractor values to JSON-able primitives."""
    if depth > _MAX_NESTING:
        return repr(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    # Rationals before float: Pillow's IFDRational is a float subclass, and the
    # "num/den" form is the raw evidence the GPS detector (TASK-02) parses.
    if _is_rational(value):
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        if len(value) > _MAX_BLOB_BYTES:
            return None  # blob: never persisted
        return value.decode("utf-8", errors="replace")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _normalize(item, depth + 1)
            if normalized is not None:
                out[str(key)] = normalized
        return out or None
    if isinstance(value, list | tuple | set | frozenset):
        items = [n for n in (_normalize(v, depth + 1) for v in value) if n is not None]
        return items or None
    return str(value)


def _is_rational(value: Any) -> bool:
    """True for IFDRational/fractions.Fraction-like values (not plain ints)."""
    return (
        not isinstance(value, int)
        and hasattr(value, "numerator")
        and hasattr(value, "denominator")
        and isinstance(value.numerator, int)
        and isinstance(value.denominator, int)
    )
