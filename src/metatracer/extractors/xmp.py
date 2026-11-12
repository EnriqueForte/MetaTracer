"""Minimal XMP packet parser shared by the PDF and image extractors.

Both pypdf and Pillow can hand us the raw XMP packet (an RDF/XML document).
Parsing it here — instead of relying on pypdf's ``XmpInformation`` or Pillow's
``getxmp()`` — gives one tested code path and consistent ``prefix:Name`` keys
(``xmp:CreatorTool``, ``dc:creator``, ``xmpMM:DocumentID``) across PDFs and
images, which is what the TASK-02 detectors expect.

The parser is deliberately small: it walks ``rdf:Description`` elements, maps
well-known namespace URIs to their conventional prefixes, flattens rdf
containers (Seq/Bag/Alt) into short JSON values and drops anything it cannot
represent as short text. It uses ``xml.etree.ElementTree``, which does not
resolve external entities. A malformed packet yields ``{}`` — a missing block
never fails the asset (TASK-01 subtask 1.4.3).
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from metatracer.core.logging import sanitize_for_log
from metatracer.extractors.sanitize import sanitize_value

logger = logging.getLogger("metatracer.extractors.xmp")

# <?xpacket ...?> processing instructions wrap the RDF document and the
# closing one sits AFTER the root element, which xml.etree rejects.
_XPACKET_PI_RE = re.compile(rb"<\?xpacket.*?\?>", re.DOTALL)

_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDF = f"{{{_RDF_NS}}}"
_RDF_CONTAINERS = frozenset({f"{_RDF}Seq", f"{_RDF}Bag", f"{_RDF}Alt"})

# Well-known XMP namespace URIs -> conventional prefixes. Unknown namespaces
# fall back to the bare local name (documented lossy case).
_NAMESPACE_PREFIXES = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.adobe.com/pdfx/1.3/": "pdfx",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://ns.adobe.com/exif/1.0/aux/": "aux",
    "http://ns.adobe.com/xap/1.0/rights/": "xmpRights",
    "http://ns.adobe.com/xap/1.0/t/": "xmpT",
    "http://ns.adobe.com/xap/1.0/t/pg/": "xmpTPg",
    "http://ns.adobe.com/xap/1.0/bj/": "xmpBJ",
    "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "Iptc4xmpCore",
    "http://iptc.org/std/Iptc4xmpExt/2008-02-29/": "Iptc4xmpExt",
}

_MAX_DEPTH = 8
# Second line of defence (threat 5). The PDF extractor caps FlateDecode
# *before* inflate (TASK-27); this check still drops an already-materialized
# packet that is larger than a legitimate XMP document (image path included).
MAX_XMP_PACKET_BYTES = 5 * 1024 * 1024


def parse_xmp_packet(packet: bytes | str) -> dict[str, str]:
    """Flatten an XMP packet into ``{prefixed_key: sanitized_value}``.

    Never raises: malformed XML, an empty packet or an oversized one returns
    an empty dict.
    """
    raw = packet.encode("utf-8", errors="replace") if isinstance(packet, str) else bytes(packet)
    if len(raw) > MAX_XMP_PACKET_BYTES:
        logger.debug("discarding oversized XMP packet (%d bytes)", len(raw))
        return {}
    raw = _XPACKET_PI_RE.sub(b"", raw).strip().strip(b"\x00").strip()
    if not raw:
        return {}
    start = raw.find(b"<")
    if start == -1:
        return {}
    try:
        root = ET.fromstring(raw[start:])
    except ET.ParseError as exc:
        logger.debug("discarding unparseable XMP packet: %s", sanitize_for_log(exc))
        return {}
    collected: dict[str, Any] = {}
    for description in root.iter(f"{_RDF}Description"):
        for attr, attr_value in description.attrib.items():
            key = _prefixed_name(attr)
            if key and attr_value and attr_value.strip():
                collected.setdefault(key, attr_value.strip())
        for child in description:
            key = _prefixed_name(child.tag)
            if not key:
                continue
            value = _element_value(child, depth=0)
            if value is not None:
                collected.setdefault(key, value)
    fields: dict[str, str] = {}
    for key, value in collected.items():
        sanitized = sanitize_value(value)
        if sanitized and sanitized.strip():
            fields[key] = sanitized
    return fields


def _prefixed_name(tag: str) -> str | None:
    """``{ns}local`` -> ``prefix:local``; RDF structural attrs return None."""
    if not tag.startswith("{"):
        return tag
    namespace, _, local = tag[1:].partition("}")
    if namespace == _RDF_NS or not local:
        return None  # rdf:about and friends are anchors, not metadata
    prefix = _NAMESPACE_PREFIXES.get(namespace)
    return f"{prefix}:{local}" if prefix else local


def _element_value(element: ET.Element, depth: int) -> Any:
    """Text, list (rdf containers) or one-level struct; None if empty."""
    if depth > _MAX_DEPTH:
        return None
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        return text or None
    if len(children) == 1 and children[0].tag in _RDF_CONTAINERS:
        items = [(li.text or "").strip() for li in children[0].findall(f"{_RDF}li")]
        return [item for item in items if item] or None
    if all(child.tag == f"{_RDF}li" for child in children):
        items = [(child.text or "").strip() for child in children]
        return [item for item in items if item] or None
    struct: dict[str, Any] = {}
    for child in children:
        key = _prefixed_name(child.tag) or child.tag
        value = _element_value(child, depth + 1)
        if value is not None:
            struct[key] = value
    return struct or None
