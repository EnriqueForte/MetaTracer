"""Normalized readings sit beside the original value and never replace it."""

from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.normalize import apply_normalization
from metatracer.extractors.pdf import pdf_timezone_status


def test_exif_gps_keeps_the_rational_and_adds_decimal_degrees() -> None:
    fields = apply_normalization(
        [
            ExtractedField("exif", "GPSLatitudeRef", "N"),
            ExtractedField("exif", "GPSLatitude", '["40/1", "24/1", "4635/100"]'),
            ExtractedField("exif", "GPSLongitudeRef", "W"),
            ExtractedField("exif", "GPSLongitude", '["3/1", "43/1", "19/1"]'),
        ]
    )
    latitude = fields[1]
    assert latitude.value == '["40/1", "24/1", "4635/100"]'
    assert latitude.value_normalized == "40.412875"
    assert latitude.normalized_kind == "decimal_degrees"
    assert fields[3].value_normalized == "-3.721944"
    assert fields[0].value_normalized is None


def test_an_exif_datetime_without_an_offset_is_unzoned() -> None:
    fields = apply_normalization(
        [ExtractedField("exif", "DateTimeOriginal", "2024:01:01 12:00:00")]
    )
    assert fields[0].value == "2024:01:01 12:00:00"
    assert fields[0].timezone_status == "unzoned"
    assert fields[0].value_normalized is None


def test_a_whole_email_is_lowercased_without_rewriting_the_original() -> None:
    fields = apply_normalization([ExtractedField("pdfinfo", "Author", "Ada@Target.Example")])
    assert fields[0].value == "Ada@Target.Example"
    assert fields[0].value_normalized == "ada@target.example"
    assert fields[0].normalized_kind == "lowercase_trim"


def test_pdf_dates_record_whether_the_offset_was_stated() -> None:
    assert pdf_timezone_status("D:20240101120000+02'00'") == "known"
    assert pdf_timezone_status("D:20240101120000Z") == "known"
    assert pdf_timezone_status("D:20240101120000") == "assumed_utc"
    assert pdf_timezone_status("D:20241399") == "invalid"
    assert pdf_timezone_status("Jane Doe") is None
