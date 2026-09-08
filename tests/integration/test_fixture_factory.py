"""Factory validation (TASK-07, subtask 7.1): real files, real extractor chain.

Each generated fixture is written to disk and pushed through the REAL
metadata extractors (TASK-01) and the REAL detector registry (TASK-02) — no
mocks — proving the factory produces files that trigger exactly their own
finding type, and that the clean pair triggers none (DoD: "el factory genera
archivos reales que disparan los 5 detectores + el caso limpio").
"""

from pathlib import Path

import pytest

from metatracer.db.models import RawMetadataItem
from metatracer.detectors.registry import DetectorRegistry
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from tests.fixtures import generate_test_fixtures as factory


def _detect(spec: factory.FixtureSpec, tmp_path: Path):
    """Extract + detect one fixture through the real TASK-01/TASK-02 chain."""
    path = tmp_path / spec.filename
    path.write_bytes(spec.builder())
    extractor = (
        PdfMetadataExtractor() if spec.filename.endswith(".pdf") else ImageMetadataExtractor()
    )
    fields = extractor.extract(path)
    items = [
        RawMetadataItem(asset_id="fixture", namespace=f.namespace, key=f.key, value=f.value)
        for f in fields
    ]
    return DetectorRegistry().detect_all(items)


@pytest.mark.parametrize(
    "spec", factory.FIXTURE_SPECS, ids=[spec.name for spec in factory.FIXTURE_SPECS]
)
def test_fixture_triggers_exactly_its_detectors(spec: factory.FixtureSpec, tmp_path: Path) -> None:
    drafts = _detect(spec, tmp_path)
    assert {draft.finding_type for draft in drafts} == spec.expected_types


def test_gps_fixture_carries_the_contract_coordinates(tmp_path: Path) -> None:
    spec = factory.spec_for("gps-photo.jpg")
    drafts = _detect(spec, tmp_path)
    assert len(drafts) == 1
    assert drafts[0].evidence_snippet == "Latitude: 40.416800, Longitude: -3.703800"
    assert drafts[0].field_source == "EXIF:GPSInfo"


def test_email_fixture_plants_the_reserved_test_domain(tmp_path: Path) -> None:
    spec = factory.spec_for("email-leak.pdf")
    drafts = _detect(spec, tmp_path)
    assert drafts
    assert all(draft.evidence_snippet == factory.TEST_EMAIL for draft in drafts)
    assert factory.TEST_EMAIL.endswith("@acme-corp.test")


def test_internal_path_fixture_leaks_the_windows_build_path(tmp_path: Path) -> None:
    spec = factory.spec_for("internal-path.pdf")
    drafts = _detect(spec, tmp_path)
    assert [draft.evidence_snippet for draft in drafts] == [factory.INTERNAL_PATH]


def test_debug_fixture_anchors_on_the_todo_comment(tmp_path: Path) -> None:
    spec = factory.spec_for("debug-comment.jpg")
    drafts = _detect(spec, tmp_path)
    assert len(drafts) == 1
    assert "TODO:" in drafts[0].evidence_snippet
    assert "JIRA-4412" in drafts[0].evidence_snippet


def test_main_writes_real_files_and_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "files"
    written = factory.main(output_dir)
    names = {path.name for path in written}
    assert names == {spec.filename for spec in factory.FIXTURE_SPECS} | {"index.html"}
    for path in written:
        assert path.stat().st_size > 0
    manifest = (output_dir / "index.html").read_text(encoding="utf-8")
    for spec in factory.FIXTURE_SPECS:
        assert spec.filename in manifest
