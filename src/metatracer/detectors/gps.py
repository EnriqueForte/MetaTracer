"""GpsDetector (TASK-02 subtask 2.1).

EXIF GPS arrives raw from TASK-01: DMS rationals as a JSON array of
``"num/den"`` strings (e.g. ``["40/1", "24/1", "4635/100"]``) plus a
hemisphere ref normalized to ``N``/``S``/``E``/``W``; the DMS -> decimal
formula is applied here. XMP GPS is already decimal, so the value is only
range-validated — the formula is never re-applied to it.

A finding requires both coordinates, finite values, lat in [-90, 90], lon in
[-180, 180] and not a null-island reading (``abs(lat) < 1e-5`` and
``abs(lon) < 1e-5``). Exact ``(0, 0)`` and near-zero rationals such as
``1/1000`` seconds are an empty GPS block, not a real place. The same
threshold is applied by :func:`classification.anchor.parse_gps_line`.
Altitude is appended to the snippet when present, without a unit: the tags
carry no unit string and inventing one is forbidden.
"""

import json
import math
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, normalize_text

EXIF_GPS_SOURCE = "EXIF:GPSInfo"
XMP_GPS_SOURCE = "XMP:GPS"

_EXIF_GPS_KEYS = frozenset(
    {
        "GPSLatitude",
        "GPSLatitudeRef",
        "GPSLongitude",
        "GPSLongitudeRef",
        "GPSAltitude",
        "GPSAltitudeRef",
    }
)
# XMP local names (the parser prefixes them "exif:", but the bare local name
# is matched so an unknown-namespace packet still yields its coordinates).
_XMP_GPS_LOCAL_KEYS = frozenset({"GPSLatitude", "GPSLongitude", "GPSAltitude"})

_HEMISPHERE_SIGNS = {"N": 1.0, "E": 1.0, "S": -1.0, "W": -1.0}

# Near (0, 0) is an empty GPS block. 1e-5 degrees is about one metre.
NULL_ISLAND_EPSILON = 1e-5


class GpsDetector:
    """Detects GPS coordinates in EXIF GPS tags and XMP ``exif:GPS*`` fields."""

    finding_type = FindingType.gps

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        exif: dict[str, str] = {}
        xmp: dict[str, str] = {}
        for item in items:
            value = normalize_text(item.value)
            if not value:
                continue
            if item.namespace == "exif" and item.key in _EXIF_GPS_KEYS:
                exif[item.key] = value
            elif item.namespace == "xmp":
                local = item.key.rpartition(":")[2]
                if local in _XMP_GPS_LOCAL_KEYS:
                    xmp[local] = value
        drafts: list[FindingDraft] = []
        exif_pair = _exif_coordinates(exif)
        if exif_pair is not None:
            drafts.append(
                _draft(exif_pair[0], exif_pair[1], exif.get("GPSAltitude"), EXIF_GPS_SOURCE)
            )
        xmp_pair = _xmp_coordinates(xmp)
        if xmp_pair is not None:
            drafts.append(_draft(xmp_pair[0], xmp_pair[1], xmp.get("GPSAltitude"), XMP_GPS_SOURCE))
        return drafts


def _draft(lat: float, lon: float, raw_altitude: str | None, source: str) -> FindingDraft:
    text = f"Latitude: {lat:.6f}, Longitude: {lon:.6f}"
    altitude = _parse_altitude(raw_altitude)
    if altitude is not None:
        text += f", Altitude: {altitude:g}"  # no unit: the tag carries none
    return FindingDraft(
        finding_type=FindingType.gps,
        field_source=source,
        evidence_snippet=text,
        confidence=Confidence.high,
    )


def _exif_coordinates(values: dict[str, str]) -> tuple[float, float] | None:
    raw_lat, raw_lon = values.get("GPSLatitude"), values.get("GPSLongitude")
    if raw_lat is None or raw_lon is None:
        return None
    lat = _dms_to_decimal(_parse_dms(values["GPSLatitude"]), values.get("GPSLatitudeRef"))
    lon = _dms_to_decimal(_parse_dms(values["GPSLongitude"]), values.get("GPSLongitudeRef"))
    if lat is None or lon is None or not _in_range(lat, lon):
        return None
    return lat, lon


def _xmp_coordinates(values: dict[str, str]) -> tuple[float, float] | None:
    raw_lat, raw_lon = values.get("GPSLatitude"), values.get("GPSLongitude")
    if raw_lat is None or raw_lon is None:
        return None
    lat = _parse_decimal(raw_lat)
    lon = _parse_decimal(raw_lon)
    if lat is None or lon is None or not _in_range(lat, lon):
        return None
    return lat, lon


def _in_range(lat: float, lon: float) -> bool:
    return (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
        and not is_null_island(lat, lon)
    )


def is_null_island(lat: float, lon: float) -> bool:
    """True when both coordinates sit on the empty-GPS neighbourhood of (0, 0)."""
    return abs(lat) < NULL_ISLAND_EPSILON and abs(lon) < NULL_ISLAND_EPSILON


def _parse_dms(raw: str) -> tuple[float, ...] | None:
    """Parse a raw EXIF DMS value: JSON array of ``"num/den"`` strings (1-3 items)."""
    try:
        parts = json.loads(raw)
    except json.JSONDecodeError:
        parts = None
    if isinstance(parts, list):
        if not 1 <= len(parts) <= 3:
            return None
        values = tuple(_parse_rational(str(part)) for part in parts)
        return values if all(value is not None for value in values) else None
    # Degrees-only scalar, as a rational ("40/1") or a plain number.
    single = _parse_rational(raw)
    return (single,) if single is not None else None


def _parse_rational(text: str) -> float | None:
    """``"num/den"`` or a plain number; None when unparseable or den == 0."""
    num, sep, den = text.strip().partition("/")
    try:
        numerator = float(num)
        denominator = float(den) if sep else 1.0
    except ValueError:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _dms_to_decimal(parts: tuple[float, ...] | None, ref: str | None) -> float | None:
    """``degrees + minutes/60 + seconds/3600``; S/W hemisphere -> negative."""
    if not parts:
        return None
    sign = _hemisphere_sign(ref)
    if sign is None:
        return None  # unrecognized ref: conservative skip, no invented sign
    degrees = parts[0]
    minutes = parts[1] if len(parts) > 1 else 0.0
    seconds = parts[2] if len(parts) > 2 else 0.0
    return sign * abs(degrees + minutes / 60.0 + seconds / 3600.0)


def _hemisphere_sign(ref: str | None) -> float | None:
    """Sign from the hemisphere ref; a missing ref means positive (documented default)."""
    if ref is None or not ref.strip():
        return 1.0
    return _HEMISPHERE_SIGNS.get(ref.strip()[0].upper())


def _parse_decimal(raw: str) -> float | None:
    """XMP decimal coordinate; an optional trailing hemisphere letter sets the sign.

    Without a hemisphere letter the value is kept exactly as written — an
    already-signed decimal must not be forced positive.
    """
    text = raw.strip()
    if text and text[-1].upper() in _HEMISPHERE_SIGNS:
        letter = text[-1].upper()
        try:
            value = float(text[:-1].strip())
        except ValueError:
            return None
        return (-1.0 if letter in ("S", "W") else 1.0) * abs(value)
    try:
        return float(text)
    except ValueError:
        return None


def _parse_altitude(raw: str | None) -> float | None:
    """Altitude as a number; accepts a rational (``"15/1"``) or a plain decimal."""
    if raw is None:
        return None
    value = _parse_rational(raw)
    if value is None or not math.isfinite(value):
        return None
    return value
