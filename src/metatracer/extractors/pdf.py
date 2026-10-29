"""PDF metadata extraction: Info dictionary + XMP packet (TASK-01 subtask 1.3).

Only metadata is read — never page content. Encrypted, truncated or otherwise
unparseable files raise :class:`ExtractionError`; the pipeline marks the asset
``failed`` and the run continues. Encrypted files are never decrypted.

The whole Info dictionary is persisted (namespace ``pdfinfo``), not just the
eight standard keys: custom entries are exactly where leaks hide, and the
TASK-02 detectors scan every value of the asset. PDF dates
(``D:YYYYMMDDHHmmSS``) become ISO 8601 UTC when parseable, otherwise the raw
string is kept.
"""

import logging
import re
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pypdf import PdfReader

from metatracer.core.exceptions import ExtractionError
from metatracer.core.logging import sanitize_for_log
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value
from metatracer.extractors.xmp import MAX_XMP_PACKET_BYTES, parse_xmp_packet

logger = logging.getLogger("metatracer.extractors.pdf")

PDFINFO_NAMESPACE = "pdfinfo"
XMP_NAMESPACE = "xmp"

_DATE_KEYS = frozenset({"CreationDate", "ModDate"})

# D:YYYYMMDDHHmmSS with optional timezone (Z or ±HH'mm'); every component
# after the year is optional in real-world files.
_PDF_DATE_RE = re.compile(
    r"^D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?\s*(Z|z|[+-]\d{1,2}'?\d{0,2}'?)?$"
)


def parse_pdf_date(raw: str) -> str:
    """Convert a PDF date string to ISO 8601 UTC; keep the raw string if unparseable.

    A date without timezone is assumed UTC (documented simplification — most
    producers that omit the offset wrote UTC).
    """
    match = _PDF_DATE_RE.match(raw.strip())
    if not match:
        return raw
    year, month, day, hour, minute, second = (
        int(group) if group else default
        for group, default in zip(match.groups()[:6], (0, 1, 1, 0, 0, 0), strict=True)
    )
    tz_text = match.group(7)
    try:
        if tz_text and tz_text not in ("Z", "z"):
            sign = 1 if tz_text[0] == "+" else -1
            digits = tz_text[1:].replace("'", "")
            hours = int(digits[:2]) if digits[:2] else 0
            minutes = int(digits[2:4]) if len(digits) >= 4 else 0
            offset = sign * timedelta(hours=hours, minutes=minutes)
            moment = datetime(year, month, day, hour, minute, second, tzinfo=UTC) - offset
        else:
            moment = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return raw  # e.g. month 19: parseable shape, impossible date
    return moment.isoformat()


def pdf_timezone_status(raw: str) -> str | None:
    """How the PDF date stated its offset, judged on the raw string.

    ``known`` when an offset or ``Z`` was present. ``assumed_utc`` when the
    date parsed and the offset was omitted. ``invalid`` when it looked like a
    PDF date and could not be read. Other strings are not dates.
    """
    text = raw.strip()
    if parse_pdf_date(text) == text:
        return "invalid" if text.startswith("D:") else None
    match = _PDF_DATE_RE.match(text)
    if match and match.group(7):
        return "known"
    return "assumed_utc"


class PdfMetadataExtractor:
    """Extracts pdfinfo + XMP fields from a PDF on disk."""

    def extract(self, path: Path) -> list[ExtractedField]:
        """Return the metadata fields of the PDF; raise ExtractionError on failure."""
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            # pypdf raises several types (PdfReadError, EmptyFileError, ValueError,
            # OSError...); all of them mean 'this asset is not parseable'.
            raise ExtractionError(
                f"cannot parse PDF: {type(exc).__name__}: {sanitize_for_log(exc)}"
            ) from exc
        if reader.is_encrypted:
            # Decryption is never attempted, not even with the empty password.
            raise ExtractionError("encrypted PDF: decryption is never attempted")
        return self._info_fields(reader) + self._xmp_fields(reader)

    def _info_fields(self, reader: PdfReader) -> list[ExtractedField]:
        try:
            info = reader.metadata
        except Exception as exc:
            logger.warning("Info dictionary unreadable: %s", sanitize_for_log(exc))
            return []
        if info is None:
            return []
        fields: list[ExtractedField] = []
        for raw_key, raw_value in info.items():
            key = raw_key.lstrip("/")
            if not key:
                continue
            value = sanitize_value(raw_value)
            if not value or not value.strip():
                continue
            if key in _DATE_KEYS:
                status = pdf_timezone_status(value)
                value = parse_pdf_date(value)
                fields.append(
                    ExtractedField(
                        PDFINFO_NAMESPACE, key, value, timezone_status=status
                    )
                )
                continue
            fields.append(ExtractedField(PDFINFO_NAMESPACE, key, value))
        return fields

    def _xmp_fields(self, reader: PdfReader) -> list[ExtractedField]:
        """Read the raw XMP packet from the catalog and parse it with the shared parser."""
        try:
            root = reader.trailer["/Root"]
            if hasattr(root, "get_object"):
                root = root.get_object()
            metadata_ref = root.get("/Metadata")
            if metadata_ref is None:
                return []
            stream = (
                metadata_ref.get_object() if hasattr(metadata_ref, "get_object") else metadata_ref
            )
            packet = _bounded_xmp_packet(stream)
        except Exception as exc:
            # A broken XMP stream must not cost the pdfinfo fields already read.
            logger.warning("XMP stream unreadable: %s", sanitize_for_log(exc))
            return []
        if not packet:
            return []
        return [
            ExtractedField(XMP_NAMESPACE, key, value)
            for key, value in parse_xmp_packet(packet).items()
        ]


def _bounded_xmp_packet(stream: object) -> bytes | None:
    """XMP bytes capped *before* inflate. ``None`` drops XMP and keeps pdfinfo.

    pypdf's ``EncodedStreamObject.get_data()`` inflates the whole Flate stream
    with no limit. This reads the raw ``_data`` (pypdf 6.x; there is no
    ``get_raw_data``) and decompresses with an output ceiling. Filters other
    than a single ``FlateDecode``, and filter chains, are discarded.
    """
    raw = getattr(stream, "_data", None)
    if not isinstance(raw, (bytes, bytearray)):
        logger.warning("discarding XMP stream: no raw bytes to bound")
        return None
    packet = bytes(raw)
    filters = _xmp_filter_names(stream)
    if filters is None:
        logger.warning("discarding XMP stream: unreadable filter")
        return None
    if not filters:
        if len(packet) > MAX_XMP_PACKET_BYTES:
            logger.warning("discarding XMP stream: uncompressed packet exceeds the size cap")
            return None
        return packet
    if filters != ["FlateDecode"]:
        logger.warning(
            "discarding XMP stream: unsupported filter %s",
            sanitize_for_log(",".join(filters)),
        )
        return None
    return _inflate_flate_capped(packet)


def _xmp_filter_names(stream: object) -> list[str] | None:
    """``/Filter`` names without the leading slash. ``None`` if unreadable."""
    getter = getattr(stream, "get", None)
    if not callable(getter):
        return None
    value = getter("/Filter")
    if value is None:
        return []
    items = list(value) if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        text = str(item).strip()
        if text.startswith("/"):
            text = text[1:]
        if not text or any(char.isspace() for char in text):
            return None
        names.append(text)
    return names


def _inflate_flate_capped(raw: bytes) -> bytes | None:
    """Decompress at most ``MAX_XMP_PACKET_BYTES`` of output. ``None`` if over."""
    decompressor = zlib.decompressobj()
    limit = MAX_XMP_PACKET_BYTES
    try:
        inflated = decompressor.decompress(raw, limit + 1)
    except zlib.error as exc:
        logger.warning("discarding XMP stream: flate decode failed: %s", sanitize_for_log(exc))
        return None
    if decompressor.unconsumed_tail or len(inflated) > limit:
        logger.warning("discarding XMP stream: decompressed packet exceeds the size cap")
        return None
    try:
        tail = decompressor.flush()
    except zlib.error as exc:
        logger.warning("discarding XMP stream: flate decode failed: %s", sanitize_for_log(exc))
        return None
    if tail:
        if len(inflated) + len(tail) > limit:
            logger.warning("discarding XMP stream: decompressed packet exceeds the size cap")
            return None
        inflated += tail
    return inflated
