"""Deterministic detectors + consolidator unit tests (TASK-02).

Covers the minimum set of the task contract: one positive per finding type, a
clean document with zero findings, email dedup across Author/Creator, a
producer without version (no software_version finding) and the (0, 0) GPS
filter — plus the DoD cases that fit the unit level. End-to-end extraction ->
detection cases use the TASK-01 fixture builders.
"""

import hashlib
from pathlib import Path

from metatracer.db.models import (
    Confidence,
    DetectorMethod,
    FindingType,
    RawMetadataItem,
)
from metatracer.detectors import (
    DebugCommentDetector,
    DetectorRegistry,
    EmailDetector,
    FindingDraft,
    GpsDetector,
    InternalPathDetector,
    SoftwareVersionDetector,
    consolidate_drafts,
    dedup_signature,
)
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

ASSET = "asset-1"


def _item(namespace: str, key: str, value: str, asset_id: str = ASSET) -> RawMetadataItem:
    return RawMetadataItem(asset_id=asset_id, namespace=namespace, key=key, value=value)


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _pdf_items(tmp_path: Path, **builder_kwargs) -> list[RawMetadataItem]:
    path = _write(tmp_path, "doc.pdf", make_pdf_bytes(**builder_kwargs))
    return [_item(f.namespace, f.key, f.value) for f in PdfMetadataExtractor().extract(path)]


# --- GpsDetector (subtask 2.1) ---


def test_gps_exif_dms_becomes_decimal() -> None:
    items = [
        _item("exif", "GPSLatitude", '["40/1", "24/1", "4635/100"]'),
        _item("exif", "GPSLatitudeRef", "N"),
        _item("exif", "GPSLongitude", '["3/1", "42/1", "7900/100"]'),
        _item("exif", "GPSLongitudeRef", "W"),
    ]
    drafts = GpsDetector().detect(items)
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.finding_type is FindingType.gps
    assert draft.field_source == "EXIF:GPSInfo"
    assert draft.evidence_snippet == "Latitude: 40.412875, Longitude: -3.721944"
    assert draft.confidence is Confidence.high
    assert draft.detector_method is DetectorMethod.rule


def test_gps_zero_zero_is_ignored() -> None:
    items = [
        _item("exif", "GPSLatitude", '["0/1", "0/1", "0/1"]'),
        _item("exif", "GPSLatitudeRef", "N"),
        _item("exif", "GPSLongitude", '["0/1", "0/1", "0/1"]'),
        _item("exif", "GPSLongitudeRef", "E"),
    ]
    assert GpsDetector().detect(items) == []


def test_gps_out_of_range_is_ignored() -> None:
    items = [
        _item("exif", "GPSLatitude", '["95/1", "0/1", "0/1"]'),
        _item("exif", "GPSLongitude", '["3/1", "0/1", "0/1"]'),
    ]
    assert GpsDetector().detect(items) == []


def test_gps_xmp_decimal_is_not_reconverted() -> None:
    items = [
        _item("xmp", "exif:GPSLatitude", "40.416775"),
        _item("xmp", "exif:GPSLongitude", "-3.703790"),
    ]
    drafts = GpsDetector().detect(items)
    assert len(drafts) == 1
    assert drafts[0].field_source == "XMP:GPS"
    assert drafts[0].evidence_snippet == "Latitude: 40.416775, Longitude: -3.703790"


def test_gps_iptc_decimal_is_honoured() -> None:
    items = [
        _item("iptc", "GPSLatitude", "40.416775"),
        _item("iptc", "GPSLongitude", "-3.703790"),
    ]
    drafts = GpsDetector().detect(items)
    assert len(drafts) == 1
    assert drafts[0].field_source == "IPTC:GPS"
    assert drafts[0].evidence_snippet == "Latitude: 40.416775, Longitude: -3.703790"


def test_gps_altitude_appended_without_invented_unit() -> None:
    items = [
        _item("exif", "GPSLatitude", '["40/1", "24/1", "4635/100"]'),
        _item("exif", "GPSLatitudeRef", "N"),
        _item("exif", "GPSLongitude", '["3/1", "42/1", "7900/100"]'),
        _item("exif", "GPSLongitudeRef", "W"),
        _item("exif", "GPSAltitude", "15/1"),
    ]
    drafts = GpsDetector().detect(items)
    assert drafts[0].evidence_snippet.endswith(", Altitude: 15")


def test_gps_end_to_end_from_jpeg_exif(tmp_path: Path) -> None:
    path = _write(tmp_path, "photo.jpg", make_jpeg_bytes())
    items = [_item(f.namespace, f.key, f.value) for f in ImageMetadataExtractor().extract(path)]
    drafts = GpsDetector().detect(items)
    assert len(drafts) == 1
    assert drafts[0].evidence_snippet == "Latitude: 40.412875, Longitude: -3.721944"


# --- EmailDetector (subtask 2.2) ---


def test_email_bare_value_high_confidence() -> None:
    drafts = EmailDetector().detect([_item("pdfinfo", "Author", "jane.doe@target.corp")])
    assert len(drafts) == 1
    assert drafts[0].finding_type is FindingType.email
    assert drafts[0].evidence_snippet == "jane.doe@target.corp"
    assert drafts[0].confidence is Confidence.high
    assert drafts[0].field_source == "pdfinfo:Author"


def test_email_embedded_in_prose_is_medium() -> None:
    drafts = EmailDetector().detect(
        [_item("pdfinfo", "Comments", "Contact jane.doe@target.corp for details")]
    )
    assert len(drafts) == 1
    assert drafts[0].evidence_snippet == "jane.doe@target.corp"
    assert drafts[0].confidence is Confidence.medium


def test_email_tool_domains_are_ignored() -> None:
    for value in ("support@adobe.com", "USER@Apple.COM", "ops@mail.microsoft.com", "a@example.org"):
        assert EmailDetector().detect([_item("pdfinfo", "Author", value)]) == []


def test_email_opensource_author_domains_are_ignored() -> None:
    """gitlab-shell run regression: bundle attribution is not a leak.

    The Sortable (rubaxa.org) and ieee754/buffer (feross.org) authors shipping
    inside GitLab's own webpack bundles are third-party credit, not target
    data — they must not surface as email findings.
    """
    cases = (
        (
            " * @author\tRubaXa   <trash@rubaxa.org>\n"
            " * @author\towenm    <owen23355@gmail.com>\n"
            " * @license MIT"
        ),
        "! * ieee754. BSD-3-Clause License. Feross Aboukhadijeh <https://feross.org/opensource>",
    )
    for value in cases:
        assert EmailDetector().detect([_item("js", "comment", value)]) == [], value


def test_email_attribution_line_is_ignored() -> None:
    """Author/credit lines (even with a non-blacklisted domain) are not a leak."""
    cases = (
        "@author   Feross Aboukhadijeh <feross@feross.org> <http://feross.org>",
        "@license MIT (c) 2022 Foo Bar <dev@example.net>",
        "Copyright 2024 Acme Corp <dev@acme.test>",
        "Contributors: jane@example.net, john@example.org",
    )
    for value in cases:
        assert EmailDetector().detect([_item("js", "comment", value)]) == [], value


def test_email_attribution_line_does_not_cancel_real_leak() -> None:
    """The attribution marker must be on the email's line, not the document."""
    value = (
        " * @author\tRubaXa   <trash@rubaxa.org>\n"
        " * (c) 2021 RubaXa\n"
        " * Fixed a bug in the internal build; contact jane.doe@target.corp"
    )
    drafts = EmailDetector().detect([_item("js", "comment", value)])
    assert len(drafts) == 1
    assert drafts[0].evidence_snippet == "jane.doe@target.corp"


def test_email_end_to_end_from_pdf(tmp_path: Path) -> None:
    items = _pdf_items(tmp_path, author="jane.doe@target.corp")
    drafts = EmailDetector().detect(items)
    assert [d.evidence_snippet for d in drafts] == ["jane.doe@target.corp"]


# --- InternalPathDetector (subtask 2.3) ---


def test_windows_users_path_exact_evidence() -> None:
    drafts = InternalPathDetector().detect(
        [_item("pdfinfo", "Comments", r"Archived at C:\Users\admin\Documents\file.pdf")]
    )
    assert len(drafts) == 1
    assert drafts[0].finding_type is FindingType.internal_path
    assert drafts[0].evidence_snippet == r"C:\Users\admin\Documents\file.pdf"
    assert drafts[0].confidence is Confidence.high


def test_windows_path_with_unix_slash() -> None:
    drafts = InternalPathDetector().detect([_item("pdfinfo", "Comments", "C:/Users/admin/x.pdf")])
    assert [d.evidence_snippet for d in drafts] == ["C:/Users/admin/x.pdf"]


def test_unc_path_is_high_confidence() -> None:
    drafts = InternalPathDetector().detect(
        [_item("pdfinfo", "Comments", r"copy to \\fileserver\shared\docs")]
    )
    assert [d.evidence_snippet for d in drafts] == [r"\\fileserver\shared\docs"]
    assert drafts[0].confidence is Confidence.high


def test_unix_paths_and_confidence_rubric() -> None:
    cases = [
        ("/home/jdoe/secret.txt", Confidence.high),
        ("/Users/jdoe/Library/x.plist", Confidence.high),
        ("/root/.ssh/config", Confidence.high),
        ("/var/www/html/index.php", Confidence.medium),
        # Subtask 2.3.5: /var/www without a *user name* is medium, whatever the
        # segment is (a deploy directory is not a user home).
        ("/var/www/intranet/site/index.php", Confidence.medium),
        ("/srv/app/releases/current", Confidence.medium),
    ]
    for value, expected in cases:
        drafts = InternalPathDetector().detect([_item("pdfinfo", "Comments", f"see {value}")])
        assert [d.evidence_snippet for d in drafts] == [value], value
        assert drafts[0].confidence is expected, value


def test_paths_in_urls_and_relative_paths_are_ignored() -> None:
    values = [
        "https://target.com/home/jdoe/secret.txt",
        "http://target.com/var/www/html",
        "file:///C:/Users/admin/x.pdf",
        "see ./images/home/icon.png",
        "installed under /opt/lampp/bin and /usr/lib",
        # XML namespace declarations (subtask 2.3.4) are never path evidence.
        'xmlns:x="/home/schemas/v1"',
        "xmlns=/Users/ns/2020",
    ]
    for value in values:
        assert InternalPathDetector().detect([_item("pdfinfo", "Comments", value)]) == [], value


def test_path_trailing_punctuation_is_stripped() -> None:
    drafts = InternalPathDetector().detect(
        [_item("pdfinfo", "Comments", r"Saved to C:\Users\admin\file.pdf.")]
    )
    assert [d.evidence_snippet for d in drafts] == [r"C:\Users\admin\file.pdf"]


def test_windows_path_end_to_end_from_pdf(tmp_path: Path) -> None:
    items = _pdf_items(tmp_path, extra_info={"/SourcePath": r"C:\Users\admin\Documents\file.pdf"})
    drafts = InternalPathDetector().detect(items)
    assert [d.evidence_snippet for d in drafts] == [r"C:\Users\admin\Documents\file.pdf"]
    assert drafts[0].field_source == "pdfinfo:SourcePath"


# --- SoftwareVersionDetector (subtask 2.4) ---


def test_software_name_with_version_is_detected() -> None:
    cases = [
        ("Producer", "Apache FOP 2.4"),
        ("Producer", "Apache FOP Version 2.6"),
        ("Producer", "wkhtmltopdf 0.12.5"),
        ("CreatorTool", "Adobe InDesign 18.2"),
        ("Software", "macOS Version 14.5 (Build 23F79)"),
    ]
    for key, value in cases:
        drafts = SoftwareVersionDetector().detect([_item("pdfinfo", key, value)])
        assert len(drafts) == 1, value
        assert drafts[0].finding_type is FindingType.software_version
        assert drafts[0].evidence_snippet == value
        assert drafts[0].confidence is Confidence.high


def test_software_without_version_is_not_a_finding() -> None:
    for value in ("Microsoft Word", "PDF", "Quartz PDFContext", "Canva", "2.4"):
        drafts = SoftwareVersionDetector().detect([_item("pdfinfo", "Producer", value)])
        assert drafts == [], value


def test_software_xmp_creator_tool_detected(tmp_path: Path) -> None:
    items = _pdf_items(tmp_path)
    drafts = SoftwareVersionDetector().detect(items)
    snippets = {d.evidence_snippet for d in drafts}
    assert "Apache FOP 2.4" in snippets  # pdfinfo Producer
    assert "UnitTest Studio 9.1" in snippets  # xmp:CreatorTool
    assert all(d.finding_type is FindingType.software_version for d in drafts)


def test_dc_creator_person_is_not_scanned_for_software() -> None:
    drafts = SoftwareVersionDetector().detect([_item("xmp", "dc:creator", '["Jane Doe 2.0"]')])
    assert drafts == []


def test_http_server_header_is_software_version() -> None:
    drafts = SoftwareVersionDetector().detect([_item("http", "server", "nginx/1.18.0")])
    assert len(drafts) == 1
    assert drafts[0].field_source == "http:server"
    assert drafts[0].evidence_snippet == "nginx/1.18.0"


def test_html_generator_is_software_version() -> None:
    drafts = SoftwareVersionDetector().detect(
        [_item("html", "meta:generator", "WordPress 6.4.2")]
    )
    assert len(drafts) == 1
    assert drafts[0].field_source == "html:meta:generator"


def test_aspnet_version_header_without_name_token() -> None:
    drafts = SoftwareVersionDetector().detect([_item("http", "x-aspnet-version", "4.0.30319")])
    assert len(drafts) == 1
    assert drafts[0].evidence_snippet == "4.0.30319"


# --- DebugCommentDetector (subtask 2.5) ---


def test_debug_strong_keywords_high_confidence() -> None:
    values = [
        "TODO: remove staging credentials",
        "fixme: broken since migration",
        "DEBUG: dump request headers",
        "XXX: revisit",
        "HACK: workaround for IE",
        "NOT FOR PUBLIC RELEASE",
        "blocked by JIRA-4521",
        "see GL-77",
        "tracked as #ISSUE-1024",
    ]
    for value in values:
        drafts = DebugCommentDetector().detect([_item("pdfinfo", "Comments", value)])
        assert len(drafts) == 1, value
        assert drafts[0].finding_type is FindingType.debug_comment
        assert drafts[0].confidence is Confidence.high


def test_debug_weak_keywords_medium_confidence() -> None:
    drafts = DebugCommentDetector().detect([_item("pdfinfo", "Subject", "CONFIDENTIAL draft")])
    assert len(drafts) == 1
    assert drafts[0].confidence is Confidence.medium


def test_debug_only_scans_free_text_fields() -> None:
    drafts = DebugCommentDetector().detect([_item("pdfinfo", "Producer", "TODO: not a comment")])
    assert drafts == []


def test_debug_one_finding_per_field_not_per_keyword() -> None:
    drafts = DebugCommentDetector().detect(
        [_item("pdfinfo", "Comments", "TODO: fix this. FIXME: and that. JIRA-9 tracks both.")]
    )
    assert len(drafts) == 1


def test_debug_snippet_window_around_match() -> None:
    value = "lorem ipsum dolor sit amet " * 10 + " TODO: fix this " + "consectetur " * 10
    drafts = DebugCommentDetector().detect([_item("pdfinfo", "Comments", value)])
    assert len(drafts) == 1
    assert len(drafts[0].evidence_snippet) <= 150
    assert "TODO: fix this" in drafts[0].evidence_snippet


def test_clean_text_yields_no_debug_finding() -> None:
    drafts = DebugCommentDetector().detect([_item("pdfinfo", "Subject", "Quarterly report 2024")])
    assert drafts == []


def test_html_and_js_comments_are_debug_findings() -> None:
    html = DebugCommentDetector().detect(
        [_item("html", "comment", "TODO: remove staging credentials")]
    )
    assert len(html) == 1
    assert html[0].field_source == "html:comment"
    js = DebugCommentDetector().detect([_item("js", "comment", "FIXME: leftover debug")])
    assert len(js) == 1
    assert js[0].field_source == "js:comment"


# --- Registry + clean document ---


def test_clean_document_yields_zero_findings(tmp_path: Path) -> None:
    items = _pdf_items(
        tmp_path,
        author="Jane Doe",
        creator="UnitTest Word",
        producer="Microsoft Word",
        xmp_packet=None,
    )
    assert DetectorRegistry().detect_all(items) == []


def test_registry_runs_all_five_detectors(tmp_path: Path) -> None:
    items = _pdf_items(
        tmp_path,
        author="jane.doe@target.corp",
        extra_info={
            "/Comments": "TODO: remove staging credentials",
            "/SourcePath": r"C:\Users\admin\Documents\file.pdf",
        },
    )
    types = {draft.finding_type for draft in DetectorRegistry().detect_all(items)}
    assert types >= {
        FindingType.email,
        FindingType.software_version,
        FindingType.debug_comment,
        FindingType.internal_path,
    }


# --- FindingConsolidator (subtask 2.6) ---


def test_signature_follows_the_contract() -> None:
    expected = hashlib.sha256(b"asset-1:email:jane@x.com").hexdigest()
    assert dedup_signature("asset-1", FindingType.email, "  Jane@X.COM ") == expected


def test_same_email_in_author_and_creator_merges_into_one_finding() -> None:
    drafts = EmailDetector().detect(
        [
            _item("pdfinfo", "Author", "jane.doe@target.corp"),
            _item("pdfinfo", "Creator", "jane.doe@target.corp"),
        ]
    )
    findings = consolidate_drafts("run-1", ASSET, drafts)
    assert len(findings) == 1
    assert findings[0].field_source == "pdfinfo:Author | pdfinfo:Creator"  # sorted, unique
    assert findings[0].severity is None  # detectors never classify
    assert findings[0].detector_method is DetectorMethod.rule


def test_merge_keeps_highest_confidence() -> None:
    drafts = [
        FindingDraft(FindingType.email, "pdfinfo:Comments", "jane@x.com", Confidence.medium),
        FindingDraft(FindingType.email, "pdfinfo:Author", "jane@x.com", Confidence.high),
    ]
    findings = consolidate_drafts("run-1", ASSET, drafts)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.high
    assert findings[0].field_source == "pdfinfo:Author | pdfinfo:Comments"


def test_different_evidence_is_not_merged() -> None:
    drafts = EmailDetector().detect(
        [
            _item("pdfinfo", "Author", "jane@target.corp"),
            _item("pdfinfo", "Author", "john@target.corp"),
        ]
    )
    findings = consolidate_drafts("run-1", ASSET, drafts)
    assert len(findings) == 2
