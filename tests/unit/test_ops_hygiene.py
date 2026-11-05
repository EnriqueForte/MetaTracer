"""TASK-41: durable scan slots, abort re-queue, /api/v1 alias, metrics text."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from metatracer.api.app import rewrite_api_v1_path
from metatracer.cli.main import app
from metatracer.core.config import Settings
from metatracer.core.exceptions import (
    RunNotFoundError,
    RunNotResumableError,
    ScanAlreadyRunningError,
)
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import Run, RunStatus
from metatracer.db.repositories import RunRepository
from metatracer.services.orchestrator import ScanOrchestratorService, ScanRequest


def _settings(**overrides) -> Settings:
    defaults = {
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "max_concurrent_runs": 1,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _request() -> ScanRequest:
    return ScanRequest(
        targets=["http://target.com/doc.pdf"],
        scope_domains=["target.com"],
        scope_confirmed=True,
    )


@pytest.fixture()
async def session_factory(tmp_path: Path):
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/ops-hygiene.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def test_api_v1_paths_rewrite_onto_api() -> None:
    assert rewrite_api_v1_path("/api/health") == "/api/health"
    assert rewrite_api_v1_path("/api/v1") == "/api"
    assert rewrite_api_v1_path("/api/v1/health") == "/api/health"
    assert rewrite_api_v1_path("/api/v1/runs/abc/abort") == "/api/runs/abc/abort"


def test_resume_help_is_registered() -> None:
    result = CliRunner().invoke(app, ["resume", "--help"])
    assert result.exit_code == 0
    assert "aborted" in result.stdout.lower()


async def test_durable_lock_sees_another_process_open_run(session_factory) -> None:
    async with session_factory() as session:
        await RunRepository(session).create(
            Run(
                target_input='["http://target.com/doc.pdf"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.running,
            )
        )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(ScanAlreadyRunningError) as excinfo:
        await orchestrator._begin_scan(_request())
    assert excinfo.value.active_run_ids


async def test_resume_requeues_an_aborted_run(session_factory) -> None:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["http://target.com/doc.pdf"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.aborted,
            )
        )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    orchestrator.start_scan = AsyncMock(return_value="new-run")
    new_id = await orchestrator.resume_scan(run.id)
    assert new_id == "new-run"
    request = orchestrator.start_scan.await_args.args[0]
    assert request.targets == ["http://target.com/doc.pdf"]
    assert request.scope_domains == ["target.com"]
    assert request.scope_confirmed is True


async def test_resume_rejects_completed_and_missing_runs(session_factory) -> None:
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["http://target.com/doc.pdf"]',
                allowed_scope='["target.com"]',
                scope_confirmed=True,
                status=RunStatus.completed,
            )
        )
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(RunNotResumableError):
        await orchestrator.resume_scan(run.id)
    with pytest.raises(RunNotFoundError):
        await orchestrator.resume_scan("missing-run")
