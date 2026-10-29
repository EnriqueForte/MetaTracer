"""Fase 3: an investigation groups runs and suggests triage. It does not apply it."""

from collections.abc import AsyncIterator
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
    Run,
    RunStatus,
    Severity,
)
from metatracer.detectors.consolidator import dedup_signature


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/investigation-test.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
        auth_enabled=False,
    )


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with application.router.lifespan_context(application):
        yield application


async def _run_with_email(session_factory, snippet: str = "ada@acme.test") -> tuple[str, str]:
    async with session_factory() as session:
        run = Run(
            target_input='["https://acme.com"]',
            allowed_scope='["acme.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
            total_findings=1,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        asset = Asset(
            run_id=run.id,
            source_url="https://acme.com/a.pdf",
            final_url="https://acme.com/a.pdf",
            content_type="application/pdf",
            file_hash_sha256=f"{run.id[:8]}{'ab' * 28}",
            file_size_bytes=10,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        finding = Finding(
            run_id=run.id,
            asset_id=asset.id,
            finding_type=FindingType.email,
            field_source="pdfinfo:Author",
            evidence_snippet=snippet,
            dedup_signature=dedup_signature(asset.id, FindingType.email, snippet),
            detector_method=DetectorMethod.rule,
            confidence=Confidence.high,
            severity=Severity.medium,
        )
        session.add(finding)
        await session.commit()
        await session.refresh(finding)
        return run.id, finding.id


async def test_confirmed_triage_is_suggested_on_the_next_run_and_not_applied(
    app: FastAPI,
) -> None:
    factory = app.state.session_factory
    run_a, finding_a = await _run_with_email(factory)
    run_b, finding_b = await _run_with_email(factory)
    run_c, _finding_c = await _run_with_email(factory)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/investigations", json={"name": "Acme 2026"})
        assert created.status_code == 201, created.text
        investigation_id = created.json()["id"]
        assert created.json()["status"] == "open"

        for run_id in (run_a, run_b):
            attached = await client.post(
                f"/api/investigations/{investigation_id}/runs", json={"run_id": run_id}
            )
            assert attached.status_code == 200, attached.text

        triaged = await client.put(
            f"/api/runs/{run_a}/findings/{finding_a}/triage",
            json={"status": "confirmed", "note": "same author as last quarter"},
        )
        assert triaged.status_code == 200, triaged.text
        assert triaged.json()["severity"] == "medium"

        suggested = await client.get(f"/api/runs/{run_b}/findings")
        assert suggested.status_code == 200, suggested.text
        row = suggested.json()["findings"][0]
        assert row["id"] == finding_b
        assert row["triage_status"] == "open"
        assert row["severity"] == "medium"
        assert row["evidence_snippet"] == "ada@acme.test"
        assert row["triage_suggestion"]["status"] == "confirmed"
        assert row["triage_suggestion"]["from_finding_id"] == finding_a
        assert row["triage_suggestion"]["note"] == "same author as last quarter"

        outsider = await client.get(f"/api/runs/{run_c}/findings")
        assert outsider.json()["findings"][0]["triage_suggestion"] is None

        other = await client.post("/api/investigations", json={"name": "Other"})
        conflict = await client.post(
            f"/api/investigations/{other.json()['id']}/runs", json={"run_id": run_b}
        )
        assert conflict.status_code == 409

        closed = await client.put(
            f"/api/investigations/{investigation_id}",
            json={"name": "Acme 2026", "description": None, "status": "closed"},
        )
        assert closed.status_code == 200, closed.text
        refused = await client.post(
            f"/api/investigations/{investigation_id}/runs", json={"run_id": run_c}
        )
        assert refused.status_code == 409
