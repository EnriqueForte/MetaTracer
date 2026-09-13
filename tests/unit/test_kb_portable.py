"""Portable KB (TASK-17, v2.2): export/import contract, validation, idempotency."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, Finding, FindingType, Run, Severity
from metatracer.db.repositories import (
    AssetRepository,
    FindingRepository,
    RunRepository,
)
from metatracer.knowledge.portable import FORMAT_VERSION, KB_NAME, export_kb, import_kb


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/kb-portable-test.db")
    await init_db(engine)
    yield engine
    await engine.dispose()


def _asset(run_id: str, name: str) -> Asset:
    return Asset(
        run_id=run_id,
        source_url=f"https://t.com/{name}.jpg",
        final_url=f"https://t.com/{name}.jpg",
        content_type="image/jpeg",
        file_hash_sha256=f"hash-{name}",
        file_size_bytes=1024,
        extraction_status="ok",
    )


def _finding(
    run_id: str,
    asset_id: str,
    finding_type: FindingType,
    snippet: str,
    *,
    severity: Severity | None,
    title: str | None = None,
) -> Finding:
    return Finding(
        run_id=run_id,
        asset_id=asset_id,
        finding_type=finding_type,
        field_source="EXIF:GPSInfo" if finding_type is FindingType.gps else "EXIF:Path",
        evidence_snippet=snippet,
        dedup_signature=f"sig-{snippet}",
        detector_method="rule",
        confidence="high",
        severity=severity,
        title=title,
    )


async def _seed(engine: AsyncEngine) -> list[Finding]:
    """One run with one gps + one internal_path finding, returns them."""
    async with create_session_factory(engine)() as session:
        run = await RunRepository(session).create(
            Run(target_input='["t.com"]', allowed_scope='["t.com"]', scope_confirmed=True)
        )
        asset = await AssetRepository(session).create(_asset(run.id, "a"))
        finding1 = await FindingRepository(session).create(
            _finding(
                run.id,
                asset.id,
                FindingType.gps,
                "Latitude: 41.6521, Longitude: -0.8809",
                severity=Severity.high,
                title="Public square GPS",
            )
        )
        finding2 = await FindingRepository(session).create(
            _finding(
                run.id,
                asset.id,
                FindingType.internal_path,
                "/home/jane/private/config",
                severity=Severity.medium,
            )
        )
        return [finding1, finding2]


async def test_export_writes_contract_json(engine: AsyncEngine, tmp_path: Path) -> None:
    await _seed(engine)
    dest = tmp_path / "kb-export.json"
    n = await export_kb(create_session_factory(engine), dest)
    assert n == 2

    payload = _read_json(dest)
    assert payload["format_version"] == FORMAT_VERSION
    assert payload["kb_name"] == KB_NAME
    assert "exported_at" in payload  # UTC ISO-8601
    entries = payload["entries"]
    assert len(entries) == 2

    # Only the portable contract keys, in every entry.
    allowed = {"finding_id", "finding_type", "evidence_snippet", "severity", "title", "created_at"}
    for entry in entries:
        assert set(entry) <= allowed
        assert "run_id" not in entry
        assert "asset_id" not in entry
        assert "field_source" not in entry
        assert "dedup_signature" not in entry
        assert "source_url" not in entry
        assert "agent_model_used" not in entry
    # The two seeded findings are present.
    types = {entry["finding_type"] for entry in entries}
    assert types == {"gps", "internal_path"}


async def test_export_empty_db_is_valid(engine: AsyncEngine, tmp_path: Path) -> None:
    dest = tmp_path / "kb-export.json"
    n = await export_kb(create_session_factory(engine), dest)
    assert n == 0
    payload = _read_json(dest)
    assert payload["entries"] == []


async def test_import_inserts_rows_with_shadow_run_asset(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    await _seed(engine)
    dest = tmp_path / "kb-export.json"
    await export_kb(create_session_factory(engine), dest)

    n = await import_kb(create_session_factory(engine), dest)
    assert n == 2

    # The imported rows exist with kb provenance and are queryable.
    async with create_session_factory(engine)() as session:
        from sqlalchemy import select

        from metatracer.db.models import Finding as F

        rows = list((await session.exec(select(F))).scalars())
    assert len(rows) == 4  # 2 original + 2 imported
    imported = [f for f in rows if f.field_source == "kb-import"]
    assert len(imported) == 2
    for f in imported:
        assert f.severity is not None
        assert f.detector_method == "heuristic"  # never re-assigned from file
    gps = next(f for f in imported if f.finding_type is FindingType.gps)
    assert gps.severity is Severity.high
    assert gps.title == "Public square GPS"


async def test_import_is_idempotent(engine: AsyncEngine, tmp_path: Path) -> None:
    await _seed(engine)
    dest = tmp_path / "kb-export.json"
    await export_kb(create_session_factory(engine), dest)
    factory = create_session_factory(engine)

    await import_kb(factory, dest)
    second = await import_kb(factory, dest)
    assert second == 0  # everything already exists -> nothing inserted

    async with create_session_factory(engine)() as session:
        from sqlalchemy import select

        from metatracer.db.models import Finding as F

        rows = list((await session.exec(select(F))).scalars())
    assert len(rows) == 4  # still 2 original + 2 imported, no third copy


async def test_import_rejects_bad_format_version(engine: AsyncEngine, tmp_path: Path) -> None:
    bad = tmp_path / "bad-version.json"
    bad.write_text('{"format_version": 99, "entries": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="format_version"):
        await import_kb(create_session_factory(engine), bad)


async def test_import_rejects_unknown_finding_type(engine: AsyncEngine, tmp_path: Path) -> None:
    bad = tmp_path / "bad-type.json"
    bad.write_text(
        '{"format_version": 1, "entries": [{"finding_id": "x", '
        '"finding_type": "bogus", "evidence_snippet": "s", "severity": null}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="finding_type"):
        await import_kb(create_session_factory(engine), bad)


async def test_import_rejects_unknown_severity(engine: AsyncEngine, tmp_path: Path) -> None:
    bad = tmp_path / "bad-sev.json"
    bad.write_text(
        '{"format_version": 1, "entries": [{"finding_id": "x", '
        '"finding_type": "gps", "evidence_snippet": "s", "severity": "severe"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="severity"):
        await import_kb(create_session_factory(engine), bad)


async def test_import_rejects_malformed_json(engine: AsyncEngine, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read knowledge-base file"):
        await import_kb(create_session_factory(engine), bad)


def _read_json(path: Path) -> dict:
    import json

    with open(path, encoding="utf-8") as fh:
        return json.load(fh)