"""TASK-35 block 35.7: triage across API, reports, dashboard, watch and CLI."""

import csv
import io
import json
from pathlib import Path

import httpx
from sqlmodel import select
from typer.testing import CliRunner

from metatracer.api.app import create_app
from metatracer.api.auth import hash_password
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
    WebhookConfig,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from metatracer.detectors import dedup_signature
from metatracer.services.watch import DeltaReporter


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/task35.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": False,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


async def _seed(
    session_factory, snippets: list[str], *, severity=Severity.high
) -> tuple[str, list[str]]:
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
                severity=severity,
            )
            session.add(finding)
            await session.commit()
            await session.refresh(finding)
            ids.append(finding.id)
        return run.id, ids


async def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_triage_persists_without_touching_severity_or_evidence(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        run_id, (fp, kept) = await _seed(
            app.state.session_factory, ["noise@acme.com", "real@acme.com"]
        )
        async with await _client(app) as client:
            response = await client.put(
                f"/api/runs/{run_id}/findings/{fp}/triage",
                json={"status": "false_positive", "note": "  vendor address  "},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["triage_status"] == "false_positive"
            assert body["triage_note"] == "vendor address"
            assert body["triaged_by"] == "local"
            assert body["triaged_at"]
            assert body["severity"] == "high"
            assert body["evidence_snippet"] == "noise@acme.com"

            bad = await client.put(
                f"/api/runs/{run_id}/findings/{fp}/triage", json={"status": "ignored"}
            )
            assert bad.status_code == 422
            smuggled = await client.put(
                f"/api/runs/{run_id}/findings/{fp}/triage",
                json={"status": "fixed", "severity": "info"},
            )
            assert smuggled.status_code == 422
            missing = await client.put(
                f"/api/runs/{run_id}/findings/nope/triage", json={"status": "fixed"}
            )
            assert missing.status_code == 404

            listing = (await client.get(f"/api/runs/{run_id}/findings")).json()
            by_id = {row["id"]: row for row in listing["findings"]}
            assert by_id[fp]["triage_status"] == "false_positive"
            assert by_id[kept]["triage_status"] == "open"
            only = (
                await client.get(f"/api/runs/{run_id}/findings?triage_status=false_positive")
            ).json()
            assert [row["id"] for row in only["findings"]] == [fp]

            stats = (await client.get("/api/stats")).json()
            assert stats["findings"]["total"] == 1
            assert stats["findings"]["dismissed"] == 1
            assert stats["findings"]["severity_breakdown"]["high"] == 1

            default_json = await client.get(f"/api/runs/{run_id}/export?format=json")
            document = json.loads(default_json.content)
            assert [row["evidence"] for row in document["findings"]] == ["real@acme.com"]
            assert document["summary"]["excluded_false_positives"] == 1

            included = await client.get(
                f"/api/runs/{run_id}/export?format=json&include_false_positives=true"
            )
            statuses = {
                row["evidence"]: row["triage_status"]
                for row in json.loads(included.content)["findings"]
            }
            assert statuses == {"noise@acme.com": "false_positive", "real@acme.com": "open"}

            for fmt in ("md", "html", "bounty"):
                text = (await client.get(f"/api/runs/{run_id}/export?format={fmt}")).text
                assert "noise@acme.com" not in text, fmt
                assert "real@acme.com" in text, fmt
                assert "Excluded as false positive: 1" in text, fmt

            rows = list(
                csv.DictReader(
                    io.StringIO(
                        (await client.get(f"/api/runs/{run_id}/export?format=csv")).content.decode(
                            "utf-8-sig"
                        )
                    )
                )
            )
            assert [row["evidence"] for row in rows] == ["real@acme.com"]
            assert rows[0]["triage_status"] == "open"


async def test_viewer_and_missing_csrf_cannot_triage(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path, auth_enabled=True, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with app.router.lifespan_context(app):
        run_id, (finding_id,) = await _seed(app.state.session_factory, ["x@acme.com"])
        async with app.state.session_factory() as db:
            db.add(
                User(
                    username="vera",
                    password_hash=hash_password("viewer-pass-1"),
                    role=UserRole.viewer,
                )
            )
            await db.commit()
        async with await _client(app) as client:
            await client.get("/api/auth/me")
            csrf = client.cookies.get("csrf_token", "")
            login = await client.post(
                "/api/auth/login",
                json={"username": "operator", "password": "test-password-123"},
                headers={"X-CSRF-Token": csrf},
            )
            assert login.status_code == 200
            no_csrf = await client.put(
                f"/api/runs/{run_id}/findings/{finding_id}/triage", json={"status": "fixed"}
            )
            assert no_csrf.status_code == 403
            session_csrf = login.json()["csrf_token"]
            ok = await client.put(
                f"/api/runs/{run_id}/findings/{finding_id}/triage",
                json={"status": "confirmed"},
                headers={"X-CSRF-Token": session_csrf},
            )
            assert ok.status_code == 200
            async with app.state.session_factory() as db:
                operator = (await db.exec(select(User).where(User.username == "operator"))).one()
            assert ok.json()["triaged_by"] == operator.id

        async with await _client(app) as viewer:
            await viewer.get("/api/auth/me")
            csrf = viewer.cookies.get("csrf_token", "")
            login = await viewer.post(
                "/api/auth/login",
                json={"username": "vera", "password": "viewer-pass-1"},
                headers={"X-CSRF-Token": csrf},
            )
            assert login.status_code == 200
            denied = await viewer.put(
                f"/api/runs/{run_id}/findings/{finding_id}/triage",
                json={"status": "fixed"},
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
            )
            assert denied.status_code == 403


async def test_false_positive_signature_is_not_new_in_the_next_watch_run(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        first_run, (fp,) = await _seed(factory, ["noise@acme.com"])
        async with await _client(app) as client:
            await client.put(
                f"/api/runs/{first_run}/findings/{fp}/triage", json={"status": "false_positive"}
            )
        second_run, _ = await _seed(factory, ["noise@acme.com"])
        delta = await DeltaReporter(factory).compute_delta(second_run)
        assert delta.new_findings == 0


async def test_compare_endpoint_and_webhook_delete_with_history(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        a, _ = await _seed(factory, ["kept@acme.com", "old@acme.com"])
        b, _ = await _seed(factory, ["kept@acme.com", "fresh@acme.com"])
        async with factory() as db:
            hook = WebhookConfig(
                name="alerts", url="https://hooks.example.com/wh", event=RunStatus.completed
            )
            db.add(hook)
            await db.commit()
            await db.refresh(hook)
            db.add(
                WebhookDelivery(
                    webhook_id=hook.id,
                    run_id=a,
                    status=WebhookDeliveryStatus.failed,
                    attempts=3,
                    max_retries=3,
                    payload_json="{}",
                )
            )
            await db.commit()
            hook_id = hook.id
        async with await _client(app) as client:
            compared = (await client.get(f"/api/compare?a={a}&b={b}")).json()
            assert [row["evidence_snippet"] for row in compared["new"]] == ["fresh@acme.com"]
            assert [row["evidence_snippet"] for row in compared["resolved"]] == ["old@acme.com"]
            assert [row["evidence_snippet"] for row in compared["persistent"]] == ["kept@acme.com"]
            assert (await client.get(f"/api/compare?a={a}&b=nope")).status_code == 404
            assert (await client.delete(f"/api/webhooks/{hook_id}")).status_code == 204
            assert (await client.get("/api/ready")).status_code == 200


def test_cli_triage_and_show_filter(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from metatracer.cli import main as cli
    from metatracer.db.engine import create_db_engine, create_session_factory, init_db

    url = f"sqlite+aiosqlite:///{tmp_path}/cli35.db"
    monkeypatch.setenv("METATRACER_DATABASE_URL", url)

    async def seed():
        engine = create_db_engine(url)
        await init_db(engine)
        try:
            return await _seed(create_session_factory(engine), ["noise@acme.com", "real@acme.com"])
        finally:
            await engine.dispose()

    run_id, (fp, _kept) = asyncio.run(seed())
    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["findings", "triage", fp, "--status", "false_positive", "--note", "vendor"]
    )
    assert result.exit_code == 0, result.output
    assert "false_positive" in result.output
    shown = runner.invoke(cli.app, ["show", run_id, "--triage", "open"])
    assert shown.exit_code == 0, shown.output
    assert "1 finding(s) (of 2)" in shown.output
    bad = runner.invoke(cli.app, ["findings", "triage", fp, "--status", "ignored"])
    assert bad.exit_code != 0
