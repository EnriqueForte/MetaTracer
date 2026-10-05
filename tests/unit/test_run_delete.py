"""TASK-30: cascade delete leaves no orphans, and retention skips recent runs."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import func, select

from metatracer.agents.knowledge import KnowledgeIndex
from metatracer.core.config import Settings
from metatracer.core.exceptions import RunActiveError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    AgentLog,
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    FeedbackVote,
    Finding,
    FindingFeedback,
    FindingType,
    RawMetadataItem,
    Run,
    RunStatus,
    Severity,
    WebhookConfig,
    WebhookDelivery,
)
from metatracer.db.repositories import RunRepository
from metatracer.services.retention import delete_run, prune_expired_runs


@pytest.fixture()
async def factory(tmp_path: Path):
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/delete.db")
    await init_db(engine)
    yield engine, create_session_factory(engine)
    await engine.dispose()


async def _count(session, model) -> int:
    result = await session.exec(select(func.count()).select_from(model))
    return int(result.one())


async def test_delete_cascade_removes_children_and_the_knowledge_index(
    factory, tmp_path: Path
) -> None:
    engine, session_factory = factory
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.example"]',
                allowed_scope='["target.example"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
        asset = Asset(
            run_id=run.id,
            source_url="https://target.example/a.pdf",
            final_url="https://target.example/a.pdf",
            content_type="application/pdf",
            file_hash_sha256="ab" * 32,
            file_size_bytes=12,
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
            evidence_snippet="ada@target.example",
            dedup_signature="sig-1",
            detector_method=DetectorMethod.rule,
            confidence=Confidence.high,
            severity=Severity.medium,
        )
        session.add(finding)
        await session.commit()
        await session.refresh(finding)
        session.add(
            RawMetadataItem(asset_id=asset.id, namespace="pdfinfo", key="Author", value="Ada")
        )
        session.add(
            FindingFeedback(
                finding_id=finding.id,
                run_id=run.id,
                vote=FeedbackVote.down,
                severity_before=Severity.high,
                severity_after=Severity.medium,
            )
        )
        session.add(
            AgentLog(
                run_id=run.id,
                finding_id=finding.id,
                prompt_tokens=1,
                completion_tokens=1,
                model_name="test",
                latency_ms=1,
                raw_response="{}",
            )
        )
        hook = WebhookConfig(
            name="alerts", url="https://hooks.example/wh", event=RunStatus.completed
        )
        session.add(hook)
        await session.commit()
        await session.refresh(hook)
        session.add(
            WebhookDelivery(webhook_id=hook.id, run_id=run.id, payload_json="{}")
        )
        await session.commit()
        run_id = run.id

    index = KnowledgeIndex(engine, session_factory)
    await index.rebuild()

    reports = tmp_path / "reports"
    reports.mkdir()
    short = run_id.split("-", 1)[0]
    report = reports / f"metatracer-target.example-{short}-20261003T000000Z.md"
    report.write_text("report", encoding="utf-8")

    await delete_run(session_factory, run_id, reports_dir=reports)

    async with session_factory() as session:
        assert await _count(session, Run) == 0
        assert await _count(session, Asset) == 0
        assert await _count(session, Finding) == 0
        assert await _count(session, RawMetadataItem) == 0
        assert await _count(session, FindingFeedback) == 0
        assert await _count(session, AgentLog) == 0
        assert await _count(session, WebhookDelivery) == 0
        assert await _count(session, WebhookConfig) == 1
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT COUNT(*) FROM knowledge_fts WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        ).scalar_one()
    assert rows == 0
    assert list(reports.iterdir()) == []


async def test_active_run_is_not_deleted(factory) -> None:
    _engine, session_factory = factory
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.example"]',
                allowed_scope='["target.example"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
    with pytest.raises(RunActiveError):
        await delete_run(session_factory, run.id)


async def test_retention_deletes_only_old_terminal_runs(factory) -> None:
    _engine, session_factory = factory
    old_start = datetime.now(UTC) - timedelta(days=40)
    async with session_factory() as session:
        repo = RunRepository(session)
        old = await repo.create(
            Run(
                target_input='["old.example"]',
                allowed_scope='["old.example"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
        old.started_at = old_start
        await repo.update(old)
        recent = await repo.create(
            Run(
                target_input='["new.example"]',
                allowed_scope='["new.example"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
        running = await repo.create(
            Run(
                target_input='["live.example"]',
                allowed_scope='["live.example"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
        running.started_at = old_start
        await repo.update(running)
        recent_id = recent.id
        running_id = running.id
    deleted = await prune_expired_runs(session_factory, retention_days=30)
    assert old.id in deleted
    async with session_factory() as session:
        repo = RunRepository(session)
        assert await repo.get(old.id) is None
        assert await repo.get(recent_id) is not None
        assert await repo.get(running_id) is not None
    assert await prune_expired_runs(session_factory, retention_days=None) == []


def test_blank_retention_setting_is_disabled() -> None:
    settings = Settings(_env_file=None, retention_days="")
    assert settings.retention_days is None
