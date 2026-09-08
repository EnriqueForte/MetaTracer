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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pypdf import PdfReader

from metatracer.core.exceptions import ExtractionError
from metatracer.core.logging import sanitize_for_log
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value
from metatracer.extractors.xmp import parse_xmp_packet

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
                value = parse_pdf_date(value)
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
            packet = stream.get_data()
        except Exception as exc:
            # A broken XMP stream must not cost the pdfinfo fields already read.
            logger.warning("XMP stream unreadable: %s", sanitize_for_log(exc))
            return []
        return [
            ExtractedField(XMP_NAMESPACE, key, value)
            for key, value in parse_xmp_packet(packet).items()
        ]
