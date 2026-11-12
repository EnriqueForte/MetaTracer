"""Fase 1 workspace endpoints: assets, raw metadata and coverage.
These tests pin the contract that makes already-extracted metadata readable:
keyset pagination without duplicates or gaps, server-side filters, 404 vs 422
semantics, and the honest coverage caveat (``counters_recorded`` is false until
the crawl budget is persisted).

Every fixture is local: an in-process ASGI app over a temp SQLite file. No
network, no mock origin.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import (
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    RawMetadataItem,
    Run,
    RunStatus,
    Severity,
    SkipReason,
)
from metatracer.extractors.sanitize import TRUNCATION_MARK


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-workspace-test.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


class Seeded:
    """Ids of the seeded run, so tests can address rows without re-querying."""

    run_id: str
    pdf_id: str
    photo_id: str
    skipped_id: str


async def _seed(app: FastAPI) -> Seeded:
    """One run: a PDF with fields, a photo with GPS, a skipped asset."""
    seeded = Seeded()
    base = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    async with app.state.session_factory() as session:
        run = Run(
            target_input='["https://acme.test/"]',
            allowed_scope='["acme.test"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        seeded.run_id = run.id

        pdf = Asset(
            run_id=run.id,
            source_url="https://acme.test/report.pdf",
            final_url="https://acme.test/report.pdf",
            content_type="application/pdf",
            file_hash_sha256="aa" * 32,
            file_size_bytes=2048,
            extraction_status=ExtractionStatus.ok,
            discovered_at=base,
        )
        photo = Asset(
            run_id=run.id,
            source_url="https://acme.test/photo.jpg",
            final_url="https://acme.test/photo.jpg",
            content_type="image/jpeg",
            file_hash_sha256="bb" * 32,
            file_size_bytes=4096,
            extraction_status=ExtractionStatus.ok,
            discovered_at=base + timedelta(seconds=1),
        )
        skipped = Asset(
            run_id=run.id,
            source_url="https://acme.test/blob.bin",
            final_url="https://acme.test/blob.bin",
            content_type="application/octet-stream",
            file_hash_sha256="cc" * 32,
            file_size_bytes=0,
            extraction_status=ExtractionStatus.skipped,
            skip_reason=SkipReason.unsupported_type,
            error_message="magic bytes match no supported type",
            discovered_at=base + timedelta(seconds=2),
        )
        session.add_all([pdf, photo, skipped])
        await session.commit()
        for asset in (pdf, photo, skipped):
            await session.refresh(asset)
        seeded.pdf_id = pdf.id
        seeded.photo_id = photo.id
        seeded.skipped_id = skipped.id

        session.add_all(
            [
                RawMetadataItem(
                    asset_id=pdf.id, namespace="pdfinfo", key="Author", value="jane@acme.test"
                ),
                RawMetadataItem(
                    asset_id=pdf.id, namespace="pdfinfo", key="Producer", value="Apache FOP 2.4"
                ),
                RawMetadataItem(
                    asset_id=pdf.id,
                    namespace="xmp",
                    key="xmp:CreatorTool",
                    value="Adobe InDesign" + TRUNCATION_MARK,
                ),
                RawMetadataItem(
                    asset_id=photo.id,
                    namespace="exif",
                    key="GPSLatitude",
                    value='["40/1", "24/1", "4635/100"]',
                ),
                RawMetadataItem(
                    asset_id=photo.id, namespace="exif", key="Make", value="Canon"
                ),
                RawMetadataItem(
                    asset_id=photo.id, namespace="http", key="server", value="nginx"
                ),
            ]
        )
        session.add(
            Finding(
                run_id=run.id,
                asset_id=pdf.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet="jane@acme.test",
                dedup_signature="sig-email",
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.medium,
            )
        )
        await session.commit()
    return seeded


# --------------------------------------------------------------------------- assets


async def test_assets_lists_every_asset_not_only_the_failed_ones(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    response = await client.get(f"/api/runs/{seeded.run_id}/assets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert [asset["source_url"] for asset in payload["assets"]] == [
        "https://acme.test/report.pdf",
        "https://acme.test/photo.jpg",
        "https://acme.test/blob.bin",
    ]
    # This is the whole point: the two OK assets were invisible before Fase 1.
    assert payload["assets"][0]["extraction_status"] == "ok"
    assert payload["assets"][2]["skip_reason"] == "unsupported_type"
    assert payload["has_more"] is False
    assert payload["next_cursor"] is None


async def test_assets_count_fields_and_findings_per_asset(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/assets")).json()
    by_url = {asset["source_url"]: asset for asset in payload["assets"]}
    assert by_url["https://acme.test/report.pdf"]["metadata_fields"] == 3
    assert by_url["https://acme.test/report.pdf"]["findings"] == 1
    assert by_url["https://acme.test/photo.jpg"]["metadata_fields"] == 3
    assert by_url["https://acme.test/photo.jpg"]["findings"] == 0
    assert by_url["https://acme.test/blob.bin"]["metadata_fields"] == 0


async def test_assets_filter_by_status_and_content_type(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    skipped = (
        await client.get(f"/api/runs/{seeded.run_id}/assets", params={"status": "skipped"})
    ).json()
    assert [asset["source_url"] for asset in skipped["assets"]] == ["https://acme.test/blob.bin"]

    images = (
        await client.get(f"/api/runs/{seeded.run_id}/assets", params={"content_type": "image/"})
    ).json()
    assert [asset["source_url"] for asset in images["assets"]] == ["https://acme.test/photo.jpg"]


async def test_assets_paginate_without_duplicates_or_gaps(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    first = (
        await client.get(f"/api/runs/{seeded.run_id}/assets", params={"limit": 2})
    ).json()
    assert len(first["assets"]) == 2
    assert first["has_more"] is True
    assert first["total"] == 3  # run-wide, not the page size

    second = (
        await client.get(
            f"/api/runs/{seeded.run_id}/assets",
            params={"limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()
    assert len(second["assets"]) == 1
    assert second["has_more"] is False

    seen = [asset["id"] for asset in first["assets"] + second["assets"]]
    assert len(seen) == len(set(seen)) == 3


async def test_assets_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs/does-not-exist/assets")
    assert response.status_code == 404


async def test_assets_malformed_cursor_is_422(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    response = await client.get(
        f"/api/runs/{seeded.run_id}/assets", params={"cursor": "not-a-cursor"}
    )
    assert response.status_code == 422


# ------------------------------------------------------------------------- metadata


async def test_metadata_lists_every_namespace_not_only_the_findings(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/metadata")).json()
    assert payload["total"] == 6
    namespaces = {item["namespace"] for item in payload["items"]}
    # None of these three produces a finding, and all three are now visible.
    assert {"pdfinfo", "xmp", "exif", "http"} <= namespaces
    # Every item carries the asset it belongs to.
    assert all(item["asset_id"] and item["asset_url"] for item in payload["items"])


async def test_metadata_flags_truncated_values(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/metadata")).json()
    by_key = {item["key"]: item for item in payload["items"]}
    assert by_key["xmp:CreatorTool"]["truncated"] is True
    assert by_key["Author"]["truncated"] is False


async def test_metadata_filters_by_namespace_and_value(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    exif = (
        await client.get(f"/api/runs/{seeded.run_id}/metadata", params={"namespace": "exif"})
    ).json()
    assert exif["total"] == 2
    assert {item["key"] for item in exif["items"]} == {"GPSLatitude", "Make"}

    # `q` matches the value OR the key, case-insensitively.
    hit_value = (
        await client.get(f"/api/runs/{seeded.run_id}/metadata", params={"q": "canon"})
    ).json()
    assert [item["value"] for item in hit_value["items"]] == ["Canon"]

    hit_key = (
        await client.get(f"/api/runs/{seeded.run_id}/metadata", params={"q": "author"})
    ).json()
    assert [item["key"] for item in hit_key["items"]] == ["Author"]


async def test_metadata_scoped_to_one_asset(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (
        await client.get(f"/api/runs/{seeded.run_id}/assets/{seeded.pdf_id}/metadata")
    ).json()
    assert payload["total"] == 3
    assert {item["key"] for item in payload["items"]} == {
        "Author",
        "Producer",
        "xmp:CreatorTool",
    }


async def test_metadata_asset_from_another_run_is_404(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    async with app.state.session_factory() as session:
        other = Run(
            target_input='["https://other.test/"]',
            allowed_scope='["other.test"]',
            scope_confirmed=True,
            status=RunStatus.completed,
        )
        session.add(other)
        await session.commit()
        await session.refresh(other)
        foreign = Asset(
            run_id=other.id,
            source_url="https://other.test/x.pdf",
            final_url="https://other.test/x.pdf",
            content_type="application/pdf",
            file_hash_sha256="dd" * 32,
            file_size_bytes=1,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(foreign)
        await session.commit()
        await session.refresh(foreign)
        foreign_id = foreign.id

    response = await client.get(f"/api/runs/{seeded.run_id}/assets/{foreign_id}/metadata")
    assert response.status_code == 404


async def test_metadata_paginates_by_id(app: FastAPI, client: httpx.AsyncClient) -> None:
    seeded = await _seed(app)
    first = (
        await client.get(f"/api/runs/{seeded.run_id}/metadata", params={"limit": 4})
    ).json()
    assert len(first["items"]) == 4
    assert first["has_more"] is True
    second = (
        await client.get(
            f"/api/runs/{seeded.run_id}/metadata",
            params={"limit": 4, "cursor": first["next_cursor"]},
        )
    ).json()
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 6


# ------------------------------------------------------------------------- coverage


async def test_coverage_splits_by_status_and_is_honest_about_limits(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/coverage")).json()
    assert payload["status"] == "completed"
    assert payload["total_assets"] == 3
    assert payload["ok"] == 2
    assert payload["skipped"] == 1
    assert payload["failed"] == 0
    assert payload["bytes_downloaded"] == 2048 + 4096
    assert payload["metadata_fields"] == 6
    assert payload["findings"] == 1
    assert payload["by_skip_reason"] == {"unsupported_type": 1}
    assert payload["by_namespace"]["pdfinfo"] == 2
    assert payload["by_content_type"]["application/pdf"] == 1
    assert payload["by_content_type"]["image/jpeg"] == 1
    assert payload["by_content_type"]["application/octet-stream"] == 1
    # Fase 2 persists the crawl budget; until then the UI must not show a zero
    # that reads as "nothing found".
    assert payload["counters_recorded"] is False
    assert payload["limits_hit"] == []


async def test_coverage_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs/nope/coverage")
    assert response.status_code == 404


async def test_coverage_reports_the_budget_and_the_limits_reached(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """Fase 2: a run with a snapshot says what it stopped at, not "unknown"."""
    seeded = await _seed(app)
    async with app.state.session_factory() as session:
        run = await session.get(Run, seeded.run_id)
        assert run is not None
        run.ingestion_stats = json.dumps(
            {
                "budget": {
                    "depth": 1,
                    "max_pages": 1,
                    "max_assets": 3,
                    "max_total_bytes": 1_000_000,
                    "max_seconds": 60,
                    "max_concurrency": 2,
                },
                "pages_crawled": 1,
                "assets_queued": 2,
                "assets_processed": 3,
                "bytes_downloaded": 6144,
                "elapsed_seconds": 1.5,
                "limits_hit": ["max_assets"],
            }
        )
        await session.commit()

    payload = (await client.get(f"/api/runs/{seeded.run_id}/coverage")).json()
    assert payload["counters_recorded"] is True
    assert payload["limits_hit"] == ["max_assets"]
    assert payload["budget"]["max_assets"] == 3
    assert payload["budget"]["depth"] == 1
    assert payload["pages_crawled"] == 1
    assert payload["assets_queued"] == 2
    assert payload["elapsed_seconds"] == 1.5
    # This snapshot predates robots accounting: null, not a fabricated zero.
    assert payload["robots_checked"] is None
    assert payload["robots_omitted"] is None


async def test_coverage_says_not_recorded_for_a_pre_fase2_run(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """A historical run must not claim zero omitted resources."""
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/coverage")).json()
    assert payload["counters_recorded"] is False
    assert payload["limits_hit"] == []
    assert payload["budget"] == {}
    assert payload["robots_checked"] is None


async def test_coverage_survives_a_corrupt_snapshot(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    async with app.state.session_factory() as session:
        run = await session.get(Run, seeded.run_id)
        assert run is not None
        run.ingestion_stats = "{not json"
        await session.commit()
    response = await client.get(f"/api/runs/{seeded.run_id}/coverage")
    assert response.status_code == 200
    assert response.json()["counters_recorded"] is False


# ------------------------------------------------------------------------- findings link


async def test_findings_expose_the_asset_they_came_from(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    seeded = await _seed(app)
    payload = (await client.get(f"/api/runs/{seeded.run_id}/findings")).json()
    assert payload["total"] == 1
    finding = payload["findings"][0]
    # The workspace links a finding back to its asset and labels its origin.
    assert finding["asset_id"] == seeded.pdf_id
    assert finding["detector_method"] == "rule"
    assert finding["created_at"]
    assert len(payload["findings"]) == 1
    assert isinstance(finding["created_at"], str)
