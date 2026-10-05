"""Evidence anchoring, anti-hallucination rule 3.2.1 (also used by TASK-05).

A finding is *anchored* when its ``evidence_snippet`` can be traced back to
the ``RawMetadataItem`` rows of its asset. Empty evidence, evidence that is
not a substring of any extracted value, or evidence that does not match the
shape of its finding type must never classify above ``info``.

Normalization mirrors the detectors: both sides are whitespace-collapsed and
casefolded before the substring test, and the ``...`` clipping markers added
by ``snippet``/``snippet_around`` at the edges are stripped first.

GPS is the one exception to the substring rule: the detector transforms raw
EXIF DMS rationals into a decimal coordinate line, so the snippet is never a
verbatim substring of the stored values. For GPS the anchor is the shape and
range check of :func:`parse_gps_line` — the detector already range-validates
coordinates and the agent stage never rewrites evidence.
"""

import re
from collections.abc import Sequence

from metatracer.db.models import Finding, FindingType, RawMetadataItem
from metatracer.detectors.base import collapse_whitespace

_SNIPPET_MARK = "..."

# The exact line shape emitted by GpsDetector; altitude is optional and kept
# lenient (``g``-formatting may use exponent notation for extreme values).
_GPS_LINE_RE = re.compile(
    r"^Latitude: (-?\d+(?:\.\d+)?), Longitude: (-?\d+(?:\.\d+)?)(?:, Altitude: \S+)?$"
)


def parse_gps_line(snippet: str) -> tuple[float, float] | None:
    """Parse a detector GPS line into ``(lat, lon)``; None when shape/range fails.

    Range rules mirror the detector: finite, lat in [-90, 90], lon in
    [-180, 180] and not a null-island reading (both axes under ``1e-5``).
    """
    from metatracer.detectors.gps import is_null_island

    match = _GPS_LINE_RE.match(snippet.strip())
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    if is_null_island(lat, lon):
        return None
    return lat, lon


def _strip_edge_markers(text: str) -> str:
    """Remove leading/trailing ``...`` clipping markers added at snippet time."""
    if text.startswith(_SNIPPET_MARK):
        text = text[len(_SNIPPET_MARK) :]
    if text.endswith(_SNIPPET_MARK):
        text = text[: -len(_SNIPPET_MARK)]
    return text.strip()


def evidence_is_anchored(finding: Finding, items: Sequence[RawMetadataItem]) -> bool:
    """True when the finding's evidence traces back to the asset's metadata."""
    snippet = finding.evidence_snippet
    if not snippet or not snippet.strip():
        return False
    if finding.finding_type is FindingType.gps:
        # DMS -> decimal transformation makes a substring test impossible.
        return parse_gps_line(snippet) is not None
    needle = _strip_edge_markers(collapse_whitespace(snippet)).casefold()
    if not needle:
        return False
    return any(needle in collapse_whitespace(item.value).casefold() for item in items if item.value)
