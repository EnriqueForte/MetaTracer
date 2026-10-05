"""TASK-28: orphan recovery, cooperative abort, and shutdown persistence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import RunNotAbortableError, RunNotFoundError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Asset, ExtractionStatus, Run, RunStatus
from metatracer.db.repositories import AssetRepository, RunRepository
from metatracer.extractors.ingest import _EXTRACTION_INCOMPLETE
from metatracer.services.notifications import NotificationBus
from metatracer.services.orchestrator import (
    INTERRUPTED_MESSAGE,
    OPERATOR_ABORT_MESSAGE,
    SHUTDOWN_ABORT_MESSAGE,
    ProgressStage,
    ScanOrchestratorService,
    ScanRequest,
)
from metatracer.services.progress import ProgressBus


def _settings(**overrides) -> Settings:
    defaults = {
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _request() -> ScanRequest:
    return ScanRequest(
        targets=["http://target.com/doc.pdf"],
        scope_domains=["target.com"],
        scope_confirmed=True,
    )


class _SlowIngestion:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, run_id: str):
        self.started.set()
        await self.release.wait()
        raise AssertionError("ingestion should have been cancelled")


class _RecordingWebhooks:
    def __init__(self) -> None:
        self.events: list[tuple[str, RunStatus]] = []

    async def enqueue_terminal(self, run_id: str, status: RunStatus, **kwargs) -> None:
        self.events.append((run_id, status))


@pytest.fixture()
async def session_factory(tmp_path: Path):
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/abort-test.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    status: RunStatus,
    started_at: datetime | None = None,
) -> Run:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["target.com"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=status,
            )
        )
        if started_at is not None:
            run.started_at = started_at
            run = await RunRepository(session).update(run)
        return run


async def test_startup_recovery_aborts_only_older_open_runs(session_factory) -> None:
    old = await _seed_run(
        session_factory,
        status=RunStatus.running,
        started_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    pending = await _seed_run(
        session_factory,
        status=RunStatus.pending,
        started_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    notifications = NotificationBus()
    webhooks = _RecordingWebhooks()
    orchestrator = ScanOrchestratorService(
        session_factory,
        _settings(),
        notifications=notifications,
        webhooks=webhooks,
    )
    fresh = await _seed_run(session_factory, status=RunStatus.running)
    recovered = await orchestrator.recover_interrupted_runs()
    assert set(recovered) == {old.id, pending.id}

    async with session_factory() as session:
        repo = RunRepository(session)
        old_row = await repo.get(old.id)
        pending_row = await repo.get(pending.id)
        fresh_row = await repo.get(fresh.id)
    assert old_row is not None and old_row.status is RunStatus.aborted
    assert old_row.error_message == INTERRUPTED_MESSAGE
    assert old_row.completed_at is not None
    assert pending_row is not None and pending_row.status is RunStatus.aborted
    assert fresh_row is not None and fresh_row.status is RunStatus.running
    assert {event.kind for event in notifications.list()} == {RunStatus.aborted}
    assert len(notifications.list()) == 2
    assert {run_id for run_id, status in webhooks.events} == {old.id, pending.id}
    assert {status for _, status in webhooks.events} == {RunStatus.aborted}


async def test_abort_emits_terminal_event_and_frees_the_slot(session_factory) -> None:
    slow = _SlowIngestion()
    bus = ProgressBus()
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), ingestion=slow
    )
    run_id = await orchestrator.start_scan(_request(), on_progress=bus.publish)
    await asyncio.wait_for(slow.started.wait(), timeout=2)
    queue = bus.subscribe(run_id)
    await orchestrator.abort(run_id)

    stages = []
    while not queue.empty():
        stages.append((await queue.get()).stage)
    assert ProgressStage.aborted in stages

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.status is RunStatus.aborted
    assert run.error_message == OPERATOR_ABORT_MESSAGE

    slow.started.clear()
    second = await orchestrator.start_scan(_request(), on_progress=bus.publish)
    await asyncio.wait_for(slow.started.wait(), timeout=2)
    assert second != run_id
    await orchestrator.shutdown()


async def test_abort_of_terminal_run_is_rejected(session_factory) -> None:
    done = await _seed_run(session_factory, status=RunStatus.completed)
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(RunNotAbortableError):
        await orchestrator.abort(done.id)
    with pytest.raises(RunNotFoundError):
        await orchestrator.abort("missing-run")


async def test_shutdown_persists_aborted(session_factory) -> None:
    slow = _SlowIngestion()
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), ingestion=slow
    )
    run_id = await orchestrator.start_scan(_request())
    await asyncio.wait_for(slow.started.wait(), timeout=2)
    await orchestrator.shutdown()
    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.status is RunStatus.aborted
    assert run.error_message == SHUTDOWN_ABORT_MESSAGE
    assert run.completed_at is not None


async def test_abort_relabels_incomplete_assets(session_factory) -> None:
    run = await _seed_run(session_factory, status=RunStatus.running)
    async with session_factory() as session:
        await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://target.com/a.pdf",
                final_url="https://target.com/a.pdf",
                content_type="application/pdf",
                file_hash_sha256="ab" * 32,
                file_size_bytes=4,
                extraction_status=ExtractionStatus.failed,
                error_message=_EXTRACTION_INCOMPLETE,
            )
        )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    await orchestrator.abort(run.id)
    async with session_factory() as session:
        assets = await AssetRepository(session).list_by_run(run.id)
    assert assets[0].extraction_status is ExtractionStatus.failed
    assert assets[0].error_message == "aborted before extraction finished"
