"""PUT/GET/DELETE /api/feedback (TASK-13, v2.1+).

Reuses the in-process ASGI setup of the other API tests. Contracts verified:
create/replace semantics, read-only GET, 404 for unknown finding / missing
feedback, 422 for same-severity or direction-mismatched corrections, and the
reason length cap.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import (
    Asset,
    Finding,
    FindingType,
    Run,
    Severity,
)
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-feedback-test.db",
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


async def _seed_finding(app: FastAPI, *, severity: Severity = Severity.high) -> Finding:
    async with app.state.session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["t.com"]',
                allowed_scope='["t.com"]',
                scope_confirmed=True,
            )
        )
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://t.com/f.jpg",
                final_url="https://t.com/f.jpg",
                content_type="image/jpeg",
                file_hash_sha256="hash-f1",
                file_size_bytes=100,
                extraction_status="ok",
            )
        )
        finding = await FindingRepository(session).create(
            Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.internal_path,
                field_source="EXIF:Path",
                evidence_snippet="/home/jane/private",
                dedup_signature="sig-1",
                detector_method="rule",
                confidence="high",
                severity=severity,
            )
        )
        return finding


async def test_put_creates_then_get_returns(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)

    response = await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "medium", "reason": "public office"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding_id"] == finding.id
    assert body["vote"] == "down"
    assert body["severity_before"] == "high"
    assert body["severity_after"] == "medium"
    assert body["reason"] == "public office"

    fetched = await client.get(f"/api/feedback/{finding.id}")
    assert fetched.status_code == 200
    assert fetched.json()["severity_after"] == "medium"


async def test_put_replaces_not_duplicates(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "medium"},
    )
    second = await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "up", "severity_after": "high", "reason": "re-checked"},
    )
    assert second.status_code == 200
    fetched = await client.get(f"/api/feedback/{finding.id}")
    assert fetched.json()["vote"] == "up"
    assert fetched.json()["severity_after"] == "high"


async def test_put_same_severity_is_422(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    response = await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "high"},  # no movement
    )
    assert response.status_code == 422


async def test_put_direction_mismatch_is_422(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    # vote=up but severity_after is lower -> contradiction
    response = await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "up", "severity_after": "medium"},
    )
    assert response.status_code == 422


async def test_put_unknown_finding_is_404(app: FastAPI, client) -> None:
    response = await client.put(
        "/api/feedback/00000000-0000-4000-8000-000000000000",
        json={"vote": "down", "severity_after": "low"},
    )
    assert response.status_code == 404


async def test_get_without_feedback_is_404(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    assert (await client.get(f"/api/feedback/{finding.id}")).status_code == 404


async def test_delete_removes_feedback(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "medium"},
    )
    assert (await client.delete(f"/api/feedback/{finding.id}")).status_code == 204
    assert (await client.get(f"/api/feedback/{finding.id}")).status_code == 404
    # deleting again is 404
    assert (await client.delete(f"/api/feedback/{finding.id}")).status_code == 404


async def test_reason_is_truncated(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    long_reason = "x" * 500
    response = await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "medium", "reason": long_reason},
    )
    assert response.status_code == 200
    assert len(response.json()["reason"]) <= 150


async def test_get_is_read_only(app: FastAPI, client) -> None:
    finding = await _seed_finding(app)
    await client.put(
        f"/api/feedback/{finding.id}",
        json={"vote": "down", "severity_after": "medium"},
    )
    before = (await client.get(f"/api/feedback/{finding.id}")).json()
    assert (await client.get(f"/api/feedback/{finding.id}")).status_code == 200
    after = (await client.get(f"/api/feedback/{finding.id}")).json()
    assert before == after