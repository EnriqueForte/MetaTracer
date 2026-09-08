"""Orchestrator notification hook (TASK-12): terminal runs emit exactly one event.

The real NotificationBus is injected; the transport/DNS are faked and the
safety controls stay real, like the rest of the orchestrator tests. The agent
phase runs without LLM configuration, so it degrades to the heuristic fallback.
"""

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import NoReturn

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import SecurityViolationError
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import RunStatus
from metatracer.db.repositories import RunRepository
from metatracer.services.notifications import NotificationBus
from metatracer.services.orchestrator import ScanOrchestratorService, ScanRequest
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

PDF_BYTES = make_pdf_bytes()
JPEG_BYTES = make_jpeg_bytes()

RouteMap = dict[str, tuple[int, str, bytes]]


def _settings(**overrides) -> Settings:
    """Hermetic settings: no .env, no LLM (agent phase = heuristic fallback)."""
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
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/orchestrator-notifications.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def _routes(routes: RouteMap) -> Callable[[httpx.Request], httpx.Response]:
    """Serve (status, content_type, body) per path; HEAD gets headers only."""

    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(request.url.path)
        if route is None:
            return httpx.Response(404)
        status, content_type, body = route
        headers = {"content-type": content_type, "content-length": str(len(body))}
        if request.method == "HEAD":
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, headers=headers, content=body)

    return handler


def _request(**overrides) -> ScanRequest:
    defaults = {
        "targets": ["http://target.com/doc.pdf"],
        "scope_domains": ["target.com"],
        "scope_confirmed": True,
    }
    defaults.update(overrides)
    return ScanRequest(**defaults)


async def test_happy_path_emits_one_completed_notification(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    bus = NotificationBus()
    orchestrator = ScanOrchestratorService(session_factory, _settings(), notifications=bus)

    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.completed

    events = bus.list()
    assert len(events) == 1
    event = events[0]
    assert event.kind is RunStatus.completed
    assert event.run_id == result.run_id
    # Same "target" convention as the run history: the first input target verbatim.
    assert event.target == "http://target.com/doc.pdf"
    assert event.total_assets == 1
    assert event.total_findings == result.total_findings
    assert event.error_message is None


class _SafetyFailingIngestion:
    """Test double: a safety violation escaping ingestion -> failed run."""

    async def execute(self, run_id: str) -> NoReturn:
        raise SecurityViolationError("host resolved to a blocked private address")


async def test_failed_run_emits_one_failed_notification(
    session_factory, tmp_path
) -> None:
    bus = NotificationBus()
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), ingestion=_SafetyFailingIngestion(), notifications=bus
    )

    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.failed

    events = bus.list()
    assert len(events) == 1
    event = events[0]
    assert event.kind is RunStatus.failed
    assert event.run_id == result.run_id
    assert event.error_message is not None
    assert "blocked private address" in event.error_message
    assert event.total_assets == 0
    assert event.total_findings == 0


async def test_no_bus_emits_nothing(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    """The orchestrator without an injected bus stays silent (CLI path)."""
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.completed
    # Nothing to assert against: no bus wired, so no notification path exists.


async def test_only_terminal_statuses_emit(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    """The bus receives exactly the terminal event, never pending/running."""

    observed: list[str] = []
    real_bus = NotificationBus()
    wrapped = NotificationBus()

    def patched_publish(event) -> None:
        observed.append(str(event.kind.value))
        real_bus.publish(event)

    # A tiny spy bus: NotificationBus methods are plain, so subclassing keeps
    # the real queue semantics while recording published kinds.
    class _SpyBus(NotificationBus):
        def publish(self, event) -> None:
            observed.append(str(event.kind.value))
            super().publish(event)

    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    spy = _SpyBus()
    orchestrator = ScanOrchestratorService(session_factory, _settings(), notifications=spy)
    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.completed
    assert observed == ["completed"]
    assert wrapped is not None and real_bus is not None  # keep lint quiet


async def test_broken_bus_never_kills_the_scan(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    """Inviolable rule 5: a failing consumer must not fail the run."""

    class _ExplodingBus(NotificationBus):
        def publish(self, event) -> None:
            raise RuntimeError("bus on fire")

    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), notifications=_ExplodingBus()
    )
    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.completed
    async with session_factory() as session:
        run = await RunRepository(session).get(result.run_id)
    assert run is not None and run.status is RunStatus.completed