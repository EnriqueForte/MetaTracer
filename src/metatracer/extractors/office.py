"""OOXML and ODF document properties (Fase 2).

The package is a ZIP. This extractor opens only the property parts
(``docProps/*.xml`` or ``meta.xml``) and never the document body, thumbnails
or embeddings. Bytes are not persisted: ``zipfile`` reads the in-memory body
and :func:`sanitize_value` keeps short text.

A ZIP that is not one of those two families raises :class:`NotOfficePackage`
so the asset is skipped as an unsupported type. A package that breaks the
size limits (too many members, a property part that declares a huge
uncompressed size or an absurd compression ratio, an encrypted part we would
have to read) raises :class:`ExtractionError`: the asset fails and the run
continues. External entities are refused before parse.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

from metatracer.core.exceptions import ExtractionError
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value

# A real deck can carry hundreds of media parts. The cap stops a central
# directory that exists only to waste time; those media parts are never opened.
MAX_ZIP_MEMBERS = 4096
# Property XML is small. The declared size is checked before inflate.
MAX_MEMBER_BYTES = 256 * 1024
MAX_RATIO = 100
MAX_FIELDS = 40
MAX_CUSTOM = 30

OOXML_NAMESPACE = "ooxml"
ODF_NAMESPACE = "odf"

_OOXML_PARTS = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")
_ODF_META = "meta.xml"
_MIMETYPE = "mimetype"

_CORE_KEYS = {
    "title": "dc:title",
    "subject": "dc:subject",
    "creator": "dc:creator",
    "description": "dc:description",
    "lastModifiedBy": "cp:lastModifiedBy",
    "revision": "cp:revision",
    "lastPrinted": "cp:lastPrinted",
    "keywords": "cp:keywords",
    "created": "dcterms:created",
    "modified": "dcterms:modified",
}
_APP_KEYS = frozenset(
    {
        "Application",
        "AppVersion",
        "Company",
        "Manager",
        "Template",
        "TotalTime",
        "Pages",
        "Words",
        "Slides",
        "Notes",
        "HiddenSlides",
        "HyperlinkBase",
        "PresentationFormat",
        "DocSecurity",
    }
)
_ODF_KEYS = {
    "generator": "meta:generator",
    "title": "dc:title",
    "subject": "dc:subject",
    "description": "dc:description",
    "creator": "dc:creator",
    "initial-creator": "meta:initial-creator",
    "creation-date": "meta:creation-date",
    "date": "dc:date",
    "editing-cycles": "meta:editing-cycles",
    "editing-duration": "meta:editing-duration",
    "printed-by": "meta:printed-by",
    "print-date": "meta:print-date",
    "keyword": "meta:keyword",
    "language": "dc:language",
}
_ODF_USER_NAME = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}name"
_TEXT_VALUES = frozenset(
    {"lpwstr", "lpstr", "i4", "bool", "date", "r8", "filetime", "cy", "decimal"}
)


class NotOfficePackage(ExtractionError):
    """ZIP bytes that are not an OOXML or ODF package."""


class OfficeMetadataExtractor:
    """Read document properties from one in-memory OOXML or ODF package."""

    def extract(self, body: bytes) -> list[ExtractedField]:
        if not body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            raise NotOfficePackage("body is not a zip package")
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile as exc:
            raise ExtractionError("office package is not a readable zip") from exc
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise ExtractionError(
                    f"office package has {len(infos)} members; cap is {MAX_ZIP_MEMBERS}"
                )
            by_name = {_safe_name(info.filename): info for info in infos}
            by_name.pop(None, None)
            family = _family(archive, by_name)
            if family == "odf":
                return _cap(_odf_fields(archive, by_name.get(_ODF_META)))
            return _cap(_ooxml_fields(archive, by_name))


def _family(archive: zipfile.ZipFile, by_name: dict[str | None, zipfile.ZipInfo]) -> str:
    mimetype = by_name.get(_MIMETYPE)
    if mimetype is not None:
        declared = _read_member(archive, mimetype)
        if declared.startswith(b"application/vnd.oasis.opendocument."):
            return "odf"
    names = {name for name in by_name if name}
    if "docProps/core.xml" in names or any(
        name.startswith(("word/", "xl/", "ppt/")) for name in names
    ):
        return "ooxml"
    raise NotOfficePackage("zip is not an OOXML or ODF package")


def _ooxml_fields(
    archive: zipfile.ZipFile, by_name: dict[str | None, zipfile.ZipInfo]
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    core = by_name.get("docProps/core.xml")
    if core is not None:
        fields.extend(_leaf_fields(OOXML_NAMESPACE, _parse(archive, core), _CORE_KEYS))
    app = by_name.get("docProps/app.xml")
    if app is not None:
        fields.extend(_app_fields(_parse(archive, app)))
    custom = by_name.get("docProps/custom.xml")
    if custom is not None:
        fields.extend(_custom_fields(_parse(archive, custom)))
    return fields


def _odf_fields(
    archive: zipfile.ZipFile, meta: zipfile.ZipInfo | None
) -> list[ExtractedField]:
    if meta is None:
        return []
    root = _parse(archive, meta)
    fields = _leaf_fields(ODF_NAMESPACE, root, _ODF_KEYS)
    for element in root.iter():
        if _local(element.tag) != "template":
            continue
        href = element.attrib.get("{http://www.w3.org/1999/xlink}href", "")
        field = _field(ODF_NAMESPACE, "meta:template", href)
        if field is not None:
            fields.append(field)
        break
    added = 0
    for element in root.iter():
        if _local(element.tag) != "user-defined" or added >= MAX_CUSTOM:
            continue
        name = (element.attrib.get(_ODF_USER_NAME) or element.attrib.get("name") or "").strip()
        field = _field(ODF_NAMESPACE, f"user-defined:{name}", element.text or "")
        if field is None or not name:
            continue
        fields.append(field)
        added += 1
    return fields


def _app_fields(root: ElementTree.Element) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for child in list(root):
        local = _local(child.tag)
        if local not in _APP_KEYS or list(child):
            continue
        field = _field(OOXML_NAMESPACE, f"app:{local}", child.text or "")
        if field is not None:
            fields.append(field)
    return fields


def _custom_fields(root: ElementTree.Element) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for element in root.iter():
        if _local(element.tag) != "property" or len(fields) >= MAX_CUSTOM:
            continue
        name = (element.attrib.get("name") or "").strip()
        if not name or len(name) > 80:
            continue
        texts = [
            (child.text or "").strip()
            for child in list(element)
            if _local(child.tag) in _TEXT_VALUES and (child.text or "").strip()
        ]
        field = _field(OOXML_NAMESPACE, f"custom:{name}", ", ".join(texts))
        if field is not None:
            fields.append(field)
    return fields


def _leaf_fields(
    namespace: str, root: ElementTree.Element, keys: dict[str, str]
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    seen: set[str] = set()
    for element in root.iter():
        local = _local(element.tag)
        key = keys.get(local)
        if key is None or key in seen or list(element):
            continue
        field = _field(namespace, key, element.text or "")
        if field is None:
            continue
        seen.add(key)
        fields.append(field)
    return fields


def _parse(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> ElementTree.Element:
    payload = _read_member(archive, info)
    lowered = payload[:64].lower()
    if b"<!doctype" in lowered or b"<!entity" in payload.lower():
        raise ExtractionError("office xml with a doctype or entity is not parsed")
    start = payload.find(b"<")
    if start < 0:
        raise ExtractionError("office property part is not xml")
    try:
        return ElementTree.fromstring(payload[start:])
    except ElementTree.ParseError as exc:
        raise ExtractionError("office property part is not well-formed xml") from exc


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    _check_member(info)
    try:
        payload = archive.read(info)
    except RuntimeError as exc:
        # zipfile raises RuntimeError for an encrypted member.
        raise ExtractionError("office property part could not be read") from exc
    if len(payload) > MAX_MEMBER_BYTES:
        raise ExtractionError("office property part expanded past the cap")
    return payload


def _check_member(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise ExtractionError("encrypted office property part is not read")
    declared = info.file_size
    compressed = info.compress_size
    if declared < 0 or declared > MAX_MEMBER_BYTES:
        raise ExtractionError("office property part declares an oversized body")
    if compressed < 0:
        raise ExtractionError("office property part has a corrupt compressed size")
    if compressed == 0:
        if declared > 0:
            raise ExtractionError("office property part declares data with no compressed size")
        return
    if declared / compressed > MAX_RATIO:
        raise ExtractionError("office property part compression ratio is not allowed")


def _safe_name(name: str) -> str | None:
    if not name or "\\" in name or name.startswith("/") or ".." in name.split("/"):
        return None
    return name


def _field(namespace: str, key: str, value: str) -> ExtractedField | None:
    text = sanitize_value(value)
    if text is None or not text.strip():
        return None
    return ExtractedField(namespace=namespace, key=key, value=text)


def _cap(fields: list[ExtractedField]) -> list[ExtractedField]:
    return fields[:MAX_FIELDS]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
