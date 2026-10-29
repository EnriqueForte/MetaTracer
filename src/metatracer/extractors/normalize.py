"""Optional normalized reading of a stored metadata value.

``ExtractedField.value`` is the sanitized original and is never replaced.
A normalized form is attached only when it is different and the conversion
is the one the detectors already use.
"""

from __future__ import annotations

import re
from dataclasses import replace

from metatracer.detectors.gps import exif_decimal_degrees, xmp_decimal_degrees
from metatracer.extractors.fields import ExtractedField

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EXIF_DATE_RE = re.compile(r"^\d{4}:\d{2}:\d{2}[ T]\d{2}:\d{2}:\d{2}$")
_EXIF_DATE_KEYS = frozenset({"DateTime", "DateTimeOriginal", "DateTimeDigitized"})
_XMP_GPS = frozenset({"GPSLatitude", "GPSLongitude"})


def apply_normalization(fields: list[ExtractedField]) -> list[ExtractedField]:
    """Return the same fields with a normalized form where one can be read."""
    refs = {
        field.key: field.value
        for field in fields
        if field.namespace == "exif" and field.key in {"GPSLatitudeRef", "GPSLongitudeRef"}
    }
    return [_annotate(field, refs) for field in fields]


def _annotate(field: ExtractedField, refs: dict[str, str]) -> ExtractedField:
    normalized = field.value_normalized
    kind = field.normalized_kind
    timezone_status = field.timezone_status
    decimal = _coordinate(field, refs)
    if decimal is not None:
        text = f"{decimal:.6f}"
        if text != field.value:
            normalized, kind = text, "decimal_degrees"
    email = _email(field.value)
    if email is not None and normalized is None:
        normalized, kind = email, "lowercase_trim"
    if (
        timezone_status is None
        and field.namespace == "exif"
        and field.key in _EXIF_DATE_KEYS
        and _EXIF_DATE_RE.match(field.value.strip())
    ):
        timezone_status = "unzoned"
    if (
        normalized == field.value_normalized
        and kind == field.normalized_kind
        and timezone_status == field.timezone_status
    ):
        return field
    return replace(
        field,
        value_normalized=normalized,
        normalized_kind=kind,
        timezone_status=timezone_status,
    )


def _coordinate(field: ExtractedField, refs: dict[str, str]) -> float | None:
    if field.namespace == "exif" and field.key == "GPSLatitude":
        return exif_decimal_degrees(field.value, refs.get("GPSLatitudeRef"))
    if field.namespace == "exif" and field.key == "GPSLongitude":
        return exif_decimal_degrees(field.value, refs.get("GPSLongitudeRef"))
    if field.namespace == "xmp":
        local = field.key.rpartition(":")[2]
        if local in _XMP_GPS:
            return xmp_decimal_degrees(field.value)
    return None


def _email(value: str) -> str | None:
    text = value.strip()
    if not _EMAIL_RE.fullmatch(text):
        return None
    lowered = text.lower()
    if lowered == value:
        return None
    return lowered
