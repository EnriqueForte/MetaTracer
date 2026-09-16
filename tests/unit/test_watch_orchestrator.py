"""Watch delta propagation through the orchestrator (TASK-22, v3.0 Eje A).

The orchestrator owns the ``watch`` flag and, on a terminal event, asks the
injected DeltaReporter for ``new_findings`` before enqueueing the webhook
delivery. These tests verify that wiring with a real DeltaReporter, real
database rows and a fake webhook dispatcher — no network ever leaves the
process.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import (
    Asset,
    Finding,
    FindingType,
    Run,
    RunStatus,
)
from metatracer.db.repositories import AssetRepository, FindingRepository, RunRepository
from metatracer.services.orchestrator import ScanOrchestratorService
from metatracer.services.watch import DeltaReporter


def _settings(**overrides) -> Settings:
    defaults = {
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/watch-orchestrator.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


class _CaptureWebhooks:
    """Stands in for WebhookDispatcher.enqueue_terminal (captures the args)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def enqueue_terminal(self, run_id: str, status, **kwargs) -> None:
        self.calls.append({"run_id": run_id, "status": status, **kwargs})


async def _seed_run_with_findings(session_factory, scope: str, signatures: list[str]) -> Run:
    """Create a completed run + one asset + the given findings (like a scan)."""
    async with session_factory() as session:
        run = await RunRepository(session).create(
            Run(
                target_input='["https://t.com/a.jpg"]',
                allowed_scope=scope,
                scope_confirmed=True,
                status=RunStatus.completed,
                total_findings=len(signatures),
            )
        )
        asset = await AssetRepository(session).create(
            Asset(
                run_id=run.id,
                source_url="https://t.com/a.jpg",
                final_url="https://t.com/a.jpg",
                content_type="image/jpeg",
                file_hash_sha256="h-a",
                file_size_bytes=10,
                extraction_status="ok",
            )
        )
        for sig in signatures:
            await FindingRepository(session).create(
                Finding(
                    run_id=run.id,
                    asset_id=asset.id,
                    finding_type=FindingType.gps,
                    field_source="EXIF:GPSInfo",
                    evidence_snippet=f"snippet-{sig}",
                    dedup_signature=sig,
                    detector_method="rule",
                    confidence="high",
                )
            )
    return run


async def test_watch_terminal_event_carries_delta_count(session_factory) -> None:
    """A terminal watch event forwards new_findings from same-scope history."""
    # One historical (non-watch) run with sig-1.
    await _seed_run_with_findings(session_factory, '["t.com"]', ["sig-1"])
    # The watch run repeats sig-1 and adds sig-2 (the only new finding).
    watch_run = await _seed_run_with_findings(
        session_factory, '["t.com"]', ["sig-1", "sig-2"]
    )

    capture = _CaptureWebhooks()
    orchestrator = ScanOrchestratorService(
        session_factory,
        _settings(),
        webhooks=capture,
        delta_reporter=DeltaReporter(session_factory),
    )
    # The watch flag is set by scan(); finalize calls the notify path. We
    # simulate the same state the scan() path establishes.
    orchestrator._active_watch = True
    await orchestrator._notify_run_finished(watch_run, RunStatus.completed, None)

    assert len(capture.calls) == 1
    call = capture.calls[0]
    assert call["run_id"] == watch_run.id
    assert call["new_findings"] == 1


async def test_non_watch_terminal_event_reports_zero_delta(session_factory) -> None:
    """Without the watch flag the terminal event reports new_findings=0."""
    run = await _seed_run_with_findings(session_factory, '["t.com"]', ["sig-1"])

    capture = _CaptureWebhooks()
    orchestrator = ScanOrchestratorService(
        session_factory,
        _settings(),
        webhooks=capture,
        delta_reporter=DeltaReporter(session_factory),
    )
    await orchestrator._notify_run_finished(run, RunStatus.completed, None)

    assert len(capture.calls) == 1
    assert capture.calls[0]["new_findings"] == 0


async def test_zero_delta_when_nothing_is_new(session_factory) -> None:
    """A repeat watch run (all signatures seen before) reports 0."""
    await _seed_run_with_findings(session_factory, '["t.com"]', ["sig-1"])
    second = await _seed_run_with_findings(session_factory, '["t.com"]', ["sig-1"])

    capture = _CaptureWebhooks()
    orchestrator = ScanOrchestratorService(
        session_factory,
        _settings(),
        webhooks=capture,
        delta_reporter=DeltaReporter(session_factory),
    )
    orchestrator._active_watch = True
    await orchestrator._notify_run_finished(second, RunStatus.completed, None)

    assert len(capture.calls) == 1
    assert capture.calls[0]["new_findings"] == 0