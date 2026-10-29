"""Extractor output contract: one sanitized metadata field, not yet persisted."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """A single metadata field produced by an extractor.

    ``namespace`` uses the contracted values (``exif``, ``xmp``, ``pdfinfo``,
    ``iptc``, ``http``, ``html``, ``js``, ``ooxml``, ``odf``); ``value`` is always sanitized text
    — never bytes — already truncated to the ~2 KB ceiling. The ingestion
    pipeline maps these to ``RawMetadataItem`` rows.
    """

    namespace: str
    key: str
    value: str
    # Optional reading aid. ``value`` stays the sanitized original.
    value_normalized: str | None = None
    normalized_kind: str | None = None
    timezone_status: str | None = None
