"""PdfMetadataExtractor / ImageMetadataExtractor / sanitizer unit tests (TASK-01).

Minimal fixture files come from tests.fixtures.builders (hand-written; the
full factory is TASK-07).
"""

import io
from datetime import UTC, datetime
from pathlib import Path

import piexif
import pytest
from PIL import Image, IptcImagePlugin
from PIL.TiffImagePlugin import IFDRational

from metatracer.core.exceptions import ExtractionError
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor, parse_pdf_date
from metatracer.extractors.sanitize import MAX_VALUE_CHARS, sanitize_value
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes, make_png_bytes


def _by_key(fields: list) -> dict[tuple[str, str], str]:
    return {(field.namespace, field.key): field.value for field in fields}


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


# --- PDF (subtask 1.3) ---


def test_pdf_info_fields_persisted(tmp_path: Path) -> None:
    path = _write(tmp_path, "doc.pdf", make_pdf_bytes())
    by_key = _by_key(PdfMetadataExtractor().extract(path))
    assert by_key[("pdfinfo", "Author")] == "Jane Doe"
    assert by_key[("pdfinfo", "Creator")] == "UnitTest Word"
    assert by_key[("pdfinfo", "Producer")] == "Apache FOP 2.4"
    assert by_key[("pdfinfo", "Title")] == "Quarterly report"


def test_pdf_dates_become_iso_utc(tmp_path: Path) -> None:
    path = _write(tmp_path, "doc.pdf", make_pdf_bytes(creation_date="D:20240101120000+02'00'"))
    by_key = _by_key(PdfMetadataExtractor().extract(path))
    # 12:00 at +02:00 is 10:00 UTC.
    assert by_key[("pdfinfo", "CreationDate")] == "2024-01-01T10:00:00+00:00"


def test_pdf_xmp_fields_persisted(tmp_path: Path) -> None:
    path = _write(tmp_path, "doc.pdf", make_pdf_bytes())
    by_key = _by_key(PdfMetadataExtractor().extract(path))
    assert by_key[("xmp", "xmp:CreatorTool")] == "UnitTest Studio 9.1"
    assert by_key[("xmp", "dc:creator")] == '["Jane Doe"]'
    assert by_key[("xmp", "xmpMM:DocumentID")] == "uuid:1234-5678"


def test_pdf_without_xmp_yields_no_xmp_fields(tmp_path: Path) -> None:
    path = _write(tmp_path, "doc.pdf", make_pdf_bytes(xmp_packet=None))
    fields = PdfMetadataExtractor().extract(path)
    assert fields  # pdfinfo still there
    assert all(field.namespace == "pdfinfo" for field in fields)


def test_damaged_pdf_raises_extraction_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "broken.pdf", b"%PDF-1.4\nthis is not a real pdf body\n")
    with pytest.raises(ExtractionError):
        PdfMetadataExtractor().extract(path)


def test_encrypted_pdf_is_never_decrypted(tmp_path: Path) -> None:
    path = _write(tmp_path, "secret.pdf", make_pdf_bytes(encrypt_password="s3cret"))
    with pytest.raises(ExtractionError, match="encrypted"):
        PdfMetadataExtractor().extract(path)


def test_parse_pdf_date_variants() -> None:
    assert parse_pdf_date("D:20240101120000Z") == "2024-01-01T12:00:00+00:00"
    assert parse_pdf_date("D:20240101120000-05'30'") == "2024-01-01T17:30:00+00:00"
    assert parse_pdf_date("D:2024") == "2024-01-01T00:00:00+00:00"
    assert parse_pdf_date("not a date") == "not a date"  # unparseable: raw string kept
    assert parse_pdf_date("D:20241399") == "D:20241399"  # impossible date: raw string kept


# --- Images (subtask 1.4) ---


def test_jpeg_exif_fields_persisted(tmp_path: Path) -> None:
    path = _write(tmp_path, "photo.jpg", make_jpeg_bytes())
    by_key = _by_key(ImageMetadataExtractor().extract(path))
    assert by_key[("exif", "Make")] == "Canon"
    assert by_key[("exif", "Model")] == "Canon EOS 80D"
    assert by_key[("exif", "Software")] == "TestSoft 1.0"
    assert by_key[("exif", "Artist")] == "Jane Doe"
    assert by_key[("exif", "DateTimeOriginal")] == "2024:01:01 11:58:00"
    assert by_key[("exif", "LensModel")] == "EF-S 18-55mm"


def test_jpeg_gps_persisted_raw(tmp_path: Path) -> None:
    """GPS stays in raw DMS form; decimal conversion is TASK-02's GpsDetector."""
    path = _write(tmp_path, "photo.jpg", make_jpeg_bytes())
    by_key = _by_key(ImageMetadataExtractor().extract(path))
    assert by_key[("exif", "GPSLatitudeRef")] == "N"
    assert by_key[("exif", "GPSLongitudeRef")] == "W"
    assert by_key[("exif", "GPSLatitude")] == '["40/1", "24/1", "4635/100"]'
    assert by_key[("exif", "GPSLongitude")] == '["3/1", "42/1", "7900/100"]'


def test_jpeg_without_exif_yields_no_fields(tmp_path: Path) -> None:
    path = _write(tmp_path, "plain.jpg", make_jpeg_bytes(with_exif=False))
    assert ImageMetadataExtractor().extract(path) == []


def test_png_xmp_from_itxt_chunk(tmp_path: Path) -> None:
    path = _write(tmp_path, "img.png", make_png_bytes())
    by_key = _by_key(ImageMetadataExtractor().extract(path))
    assert by_key[("xmp", "xmp:CreatorTool")] == "UnitTest Studio 9.1"
    assert by_key[("xmp", "dc:creator")] == '["Jane Doe"]'


def test_iptc_fields_mapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """IPTC IIM datasets map to names; unknown datasets keep record:dataset."""
    monkeypatch.setattr(
        IptcImagePlugin,
        "getiptcinfo",
        lambda _img: {(2, 80): b"Jane Doe", (2, 120): b"Offsite caption", (9, 1): b"x"},
    )
    path = _write(tmp_path, "photo.jpg", make_jpeg_bytes())
    by_key = _by_key(ImageMetadataExtractor().extract(path))
    assert by_key[("iptc", "Byline")] == "Jane Doe"
    assert by_key[("iptc", "CaptionAbstract")] == "Offsite caption"
    assert by_key[("iptc", "9:1")] == "x"


def test_broken_image_raises_extraction_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "broken.jpg", b"\xff\xd8\xff not really a jpeg")
    with pytest.raises(ExtractionError):
        ImageMetadataExtractor().extract(path)


def test_no_binary_blobs_persisted(tmp_path: Path) -> None:
    """An ICC profile embedded in the file never reaches the field list."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, "jpeg", icc_profile=b"\x00" * 5000)
    path = _write(tmp_path, "icc.jpg", buffer.getvalue())
    fields = ImageMetadataExtractor().extract(path)
    assert all(field.key != "icc_profile" for field in fields)
    assert all(len(field.value) <= MAX_VALUE_CHARS for field in fields)


# --- Sanitizer (subtask 1.4.4) ---


def test_sanitize_value_conversions() -> None:
    assert sanitize_value("plain") == "plain"
    assert sanitize_value(None) is None
    assert sanitize_value(b"caf\xc3\xa9") == "café"  # valid UTF-8
    assert sanitize_value(b"\xff\xfe") == "��"  # invalid UTF-8 -> replacement chars
    assert sanitize_value(IFDRational(4635, 100)) == "4635/100"
    assert sanitize_value((IFDRational(40, 1), IFDRational(24, 1))) == '["40/1", "24/1"]'
    assert sanitize_value(datetime(2024, 1, 1, tzinfo=UTC)) == "2024-01-01T00:00:00+00:00"
    assert sanitize_value({"a": 1}) == '{"a": 1}'


def test_sanitize_value_refuses_blobs_and_truncates() -> None:
    assert sanitize_value(b"x" * 5000) is None  # oversized bytes: blob, refused
    truncated = sanitize_value("y" * 5000)
    assert truncated is not None
    assert len(truncated) == MAX_VALUE_CHARS
    assert truncated.endswith("[truncated]")


def test_piexif_constants_sanity() -> None:
    """Guard the fixture builder against silent piexif API drift."""
    assert piexif.GPSIFD.GPSLatitude == 2
    assert piexif.GPSIFD.GPSLongitudeRef == 3


def test_oversized_xmp_packet_is_dropped() -> None:
    """Decompression amplification guard: huge packets are not parsed."""
    from metatracer.extractors.xmp import MAX_XMP_PACKET_BYTES, parse_xmp_packet

    assert parse_xmp_packet(b"<" + b"x" * MAX_XMP_PACKET_BYTES) == {}
    assert parse_xmp_packet(b"") == {}
    assert parse_xmp_packet(b"not xml at all") == {}
