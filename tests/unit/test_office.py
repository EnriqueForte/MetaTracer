"""OOXML/ODF properties: metadata only, with zip-bomb limits."""

import io
import zipfile

import pytest

from metatracer.core.exceptions import ExtractionError
from metatracer.extractors.crawler import reference_kind
from metatracer.extractors.office import (
    MAX_ZIP_MEMBERS,
    ODF_NAMESPACE,
    OOXML_NAMESPACE,
    NotOfficePackage,
    OfficeMetadataExtractor,
    _check_member,
)
from metatracer.extractors.sniff import AssetKind, classify_downloaded_asset, worth_fetching

_CORE = b"""<?xml version="1.0"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator>jane@acme.test</dc:creator>
  <cp:lastModifiedBy>bob</cp:lastModifiedBy>
  <cp:revision>4</cp:revision>
</cp:coreProperties>
"""
_APP = b"""<?xml version="1.0"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Office Word</Application>
  <Company>Acme</Company>
  <Template>Normal.dotm</Template>
  <TitlesOfParts><vt:vector xmlns:vt="http://example"><vt:lpstr>SECRET-BODY-TOKEN</vt:lpstr></vt:vector></TitlesOfParts>
</Properties>
"""
_CUSTOM = b"""<?xml version="1.0"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <property name="Owner"><vt:lpwstr>ada@acme.test</vt:lpwstr></property>
</Properties>
"""
_BODY = b"<document>SECRET-BODY-TOKEN</document>"


def _package(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _docx() -> bytes:
    return _package(
        {
            "word/document.xml": _BODY,
            "docProps/core.xml": _CORE,
            "docProps/app.xml": _APP,
            "docProps/custom.xml": _CUSTOM,
            "../secrets.txt": b"SHOULD-NOT-READ",
        }
    )


def test_ooxml_keeps_properties_and_drops_the_body() -> None:
    fields = OfficeMetadataExtractor().extract(_docx())
    found = {field.key: field.value for field in fields}
    assert all(field.namespace == OOXML_NAMESPACE for field in fields)
    assert found["dc:creator"] == "jane@acme.test"
    assert found["cp:lastModifiedBy"] == "bob"
    assert found["app:Company"] == "Acme"
    assert found["app:Template"] == "Normal.dotm"
    assert found["custom:Owner"] == "ada@acme.test"
    assert "SECRET-BODY-TOKEN" not in found.values()
    assert "SHOULD-NOT-READ" not in found.values()
    assert "app:TitlesOfParts" not in found


def test_odf_reads_meta_and_a_template_path() -> None:
    meta = b"""<?xml version="1.0"?>
    <office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
     xmlns:xlink="http://www.w3.org/1999/xlink">
      <office:meta>
        <meta:generator>LibreOffice/7.6</meta:generator>
        <dc:creator>jane@acme.test</dc:creator>
        <meta:initial-creator>ada</meta:initial-creator>
        <meta:template xlink:href="file:///C:/Users/ada/template.ott"/>
        <meta:user-defined meta:name="Editor">bob@acme.test</meta:user-defined>
      </office:meta>
      <office:body>SECRET-BODY-TOKEN</office:body>
    </office:document-meta>
    """
    body = _package(
        {
            "mimetype": b"application/vnd.oasis.opendocument.text",
            "meta.xml": meta,
            "content.xml": b"<doc>SECRET-BODY-TOKEN</doc>",
        }
    )
    fields = OfficeMetadataExtractor().extract(body)
    found = {field.key: field.value for field in fields}
    assert all(field.namespace == ODF_NAMESPACE for field in fields)
    assert found["meta:generator"] == "LibreOffice/7.6"
    assert found["dc:creator"] == "jane@acme.test"
    assert found["meta:initial-creator"] == "ada"
    assert found["meta:template"] == "file:///C:/Users/ada/template.ott"
    assert found["user-defined:Editor"] == "bob@acme.test"
    assert "SECRET-BODY-TOKEN" not in found.values()


def test_random_zip_is_not_an_office_package() -> None:
    body = _package({"readme.txt": b"hello"})
    with pytest.raises(NotOfficePackage):
        OfficeMetadataExtractor().extract(body)


def test_oversized_and_high_ratio_members_are_refused_before_inflate() -> None:
    huge = zipfile.ZipInfo("docProps/core.xml")
    huge.file_size = 50 * 1024 * 1024
    huge.compress_size = 40
    with pytest.raises(ExtractionError, match="oversized"):
        _check_member(huge)
    dense = zipfile.ZipInfo("docProps/core.xml")
    dense.file_size = 100_000
    dense.compress_size = 10
    with pytest.raises(ExtractionError, match="ratio"):
        _check_member(dense)


def test_encrypted_property_part_is_not_read() -> None:
    info = zipfile.ZipInfo("docProps/core.xml")
    info.flag_bits = 0x1
    info.file_size = 20
    info.compress_size = 20
    with pytest.raises(ExtractionError, match="encrypted"):
        _check_member(info)


def test_too_many_members_fails_the_asset() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<w/>")
        for index in range(MAX_ZIP_MEMBERS):
            archive.writestr(f"word/media/{index}.bin", b"x")
    with pytest.raises(ExtractionError, match="members"):
        OfficeMetadataExtractor().extract(buffer.getvalue())


def test_doctype_is_not_parsed() -> None:
    hostile = b'<!DOCTYPE a [<!ENTITY x "y">]><a/>'
    body = _package({"docProps/core.xml": hostile, "word/document.xml": b"<w/>"})
    with pytest.raises(ExtractionError, match="doctype"):
        OfficeMetadataExtractor().extract(body)


def test_classification_accepts_a_zip_docx_and_rejects_html_and_plain_zip() -> None:
    header = b"PK\x03\x04" + b"\x00" * 12
    docx = classify_downloaded_asset(header, url="https://target.com/a.docx")
    assert docx is AssetKind.office
    html = b"<html><body>nope</body></html>"
    assert classify_downloaded_asset(html, url="https://t/a.docx") is None
    assert classify_downloaded_asset(header, url="https://target.com/files.zip") is None
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    extensionless = classify_downloaded_asset(header, content_type=mime, url="https://t/download")
    assert extensionless is AssetKind.office
    assert worth_fetching(mime) is True
    assert worth_fetching("application/zip") is False
    assert reference_kind("https://target.com/report.docx") == "document"
    assert reference_kind("https://target.com/sheet.ods") == "document"
