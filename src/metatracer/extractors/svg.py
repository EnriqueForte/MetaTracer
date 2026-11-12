"""SVG metadata extraction (TASK-48): RDF / Dublin Core only, never drawing markup.

The raster-or-vector drawing (``path``, ``g``, ``rect``, inline ``<title>`` used
as an accessible name) is not persisted. Only the ``<metadata>`` subtree is
walked; RDF packets go through the shared XMP parser. A buffer that cannot be
parsed as XML fails the asset without aborting the run.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from metatracer.core.exceptions import ExtractionError
from metatracer.core.logging import sanitize_for_log
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value
from metatracer.extractors.xmp import parse_xmp_packet

_SVG_NS = "http://www.w3.org/2000/svg"
_XMP_NAMESPACE = "xmp"


class SvgMetadataExtractor:
    """Reads Dublin Core / RDF from an SVG ``<metadata>`` block."""

    def extract(self, body: bytes) -> list[ExtractedField]:
        raw = body.lstrip()
        if b"<svg" not in raw[:8192].lower():
            raise ExtractionError("svg root not found in lookahead")
        start = raw.find(b"<")
        if start == -1:
            raise ExtractionError("svg is not XML")
        try:
            root = ET.fromstring(raw[start:])
        except ET.ParseError as exc:
            raise ExtractionError(
                f"cannot parse svg: {type(exc).__name__}: {sanitize_for_log(exc)}"
            ) from exc
        if _local_name(root.tag).lower() != "svg":
            raise ExtractionError("xml root is not svg")
        collected: dict[str, str] = {}
        for metadata in root.iter(f"{{{_SVG_NS}}}metadata"):
            inner = ET.tostring(metadata, encoding="utf-8")
            collected.update(parse_xmp_packet(inner))
            for child in metadata.iter():
                key = _prefixed_dc(child.tag)
                if key is None:
                    continue
                text = "".join(child.itertext()).strip()
                sanitized = sanitize_value(text)
                if sanitized:
                    collected.setdefault(key, sanitized)
        return [ExtractedField(_XMP_NAMESPACE, key, value) for key, value in collected.items()]


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.partition("}")[2]
    return tag


def _prefixed_dc(tag: str) -> str | None:
    """Keep Dublin Core local names when the XMP parser missed a wrapper."""
    if not tag.startswith("{"):
        return None
    namespace, _, local = tag[1:].partition("}")
    if namespace != "http://purl.org/dc/elements/1.1/" or not local:
        return None
    return f"dc:{local}"
