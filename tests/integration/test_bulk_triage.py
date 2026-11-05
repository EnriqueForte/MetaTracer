"""TASK-42: bulk triage. Same states, CSRF, no severity/evidence mutation."""

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from metatracer.api.app import create_app
from metatracer.api.auth import hash_password
from metatracer.cli import main as cli
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
    User,
    UserRole,
)
from metatracer.detectors import dedup_signature


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/bulk-triage.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


async def _seed(session_factory, snippets: list[str]) -> tuple[str, list[str]]:
    async with session_factory() as session:
        run = Run(
            target_input='["https://acme.com"]',
            allowed_scope='["acme.com"]',
            scope_confirmed=True,
            status=RunStatus.completed,
            total_findings=len(snippets),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        asset = Asset(
            run_id=run.id,
            source_url="https://acme.com/a.pdf",
            final_url="https://acme.com/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="ab" * 32,
            file_size_bytes=10,
            extraction_status=ExtractionStatus.ok,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        ids = []
        for snippet in snippets:
            finding = Finding(
                run_id=run.id,
                asset_id=asset.id,
                finding_type=FindingType.email,
                field_source="pdfinfo:Author",
                evidence_snippet=snippet,
                dedup_signature=dedup_signature(asset.id, FindingType.email, snippet),
                detector_method=DetectorMethod.rule,
                confidence=Confidence.high,
                severity=Severity.high,
            )
            session.add(finding)
            await session.commit()
            await session.refresh(finding)
            ids.append(finding.id)
        return run.id, ids


async def test_bulk_triage_does_not_touch_severity_or_evidence(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        run_id, ids = await _seed(app.state.session_factory, ["a@acme.com", "b@acme.com"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            forbidden = await client.post(
                f"/api/runs/{run_id}/findings/triage",
                json={
                    "finding_ids": ids,
                    "status": "false_positive",
                    "severity": "low",
                },
            )
            assert forbidden.status_code == 422
            response = await client.post(
                f"/api/runs/{run_id}/findings/triage",
                json={"finding_ids": ids, "status": "false_positive", "note": "vendor"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["updated"] == 2
            assert body["missing"] == []
            assert body["triage_status"] == "false_positive"
            for row in body["findings"]:
                assert row["severity"] == "high"
                assert row["evidence_snippet"] in {"a@acme.com", "b@acme.com"}
                assert row["triage_status"] == "false_positive"
                assert row["triage_note"] == "vendor"


async def test_bulk_triage_reports_missing_ids(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        run_id, ids = await _seed(app.state.session_factory, ["a@acme.com"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/runs/{run_id}/findings/triage",
                json={"finding_ids": [ids[0], "missing-id"], "status": "fixed"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["updated"] == 1
            assert body["missing"] == ["missing-id"]


async def test_bulk_triage_viewer_and_missing_csrf_are_forbidden(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with app.router.lifespan_context(app):
        run_id, ids = await _seed(app.state.session_factory, ["x@acme.com"])
        async with app.state.session_factory() as db:
            db.add(
                User(
                    username="vera",
                    password_hash=hash_password("viewer-pass-1"),
                    role=UserRole.viewer,
                )
            )
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/api/auth/me")
            csrf = client.cookies.get("csrf_token", "")
            login = await client.post(
                "/api/auth/login",
                json={"username": "operator", "password": "test-password-123"},
                headers={"X-CSRF-Token": csrf},
            )
            assert login.status_code == 200
            no_csrf = await client.post(
                f"/api/runs/{run_id}/findings/triage",
                json={"finding_ids": ids, "status": "fixed"},
            )
            assert no_csrf.status_code == 403
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as viewer:
            await viewer.get("/api/auth/me")
            csrf = viewer.cookies.get("csrf_token", "")
            login = await viewer.post(
                "/api/auth/login",
                json={"username": "vera", "password": "viewer-pass-1"},
                headers={"X-CSRF-Token": csrf},
            )
            assert login.status_code == 200
            denied = await viewer.post(
                f"/api/runs/{run_id}/findings/triage",
                json={"finding_ids": ids, "status": "fixed"},
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
            )
            assert denied.status_code == 403


def test_cli_bulk_triage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "cli-bulk.db"
    monkeypatch.setenv("METATRACER_DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("METATRACER_LLM_API_KEY", "")
    monkeypatch.setenv("METATRACER_LLM_BASE_URL", "")
    monkeypatch.setenv("METATRACER_LLM_MODEL", "")

    import asyncio

    from metatracer.db.engine import create_db_engine, create_session_factory, init_db

    async def seed() -> tuple[str, list[str]]:
        engine = create_db_engine(f"sqlite+aiosqlite:///{db}")
        await init_db(engine)
        factory = create_session_factory(engine)
        run_id, ids = await _seed(factory, ["cli@acme.com", "cli2@acme.com"])
        await engine.dispose()
        return run_id, ids

    _run_id, ids = asyncio.run(seed())
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["findings", "bulk-triage", *ids, "--status", "confirmed", "--note", "batch"],
    )
    assert result.exit_code == 0, result.output
    assert "Triaged 2 finding(s) as confirmed" in result.output
