"""ScanOrchestratorService: scope gate, run lifecycle and concurrency (TASK-06, 6.1).

Covers the DoD items of subtask 6.1: without ``scope_confirmed`` there is no
HTTP and no persisted Run; a safety exception escaping a stage marks the run
``failed`` with a clear message; a happy path over a mocked transport reaches
``completed`` with reports written; zero findings is a valid completed run;
and a second concurrent scan is rejected. DNS and transport are faked;
ScopeValidator and NetworkSafetyGuard are the real ones. The agent phase runs
without LLM configuration, so it degrades to the heuristic fallback.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import NoReturn

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.config import Settings
from metatracer.core.exceptions import (
    MetaTracerError,
    ScanAlreadyRunningError,
    ScopeNotConfirmedError,
    SecurityViolationError,
)
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import RunStatus
from metatracer.db.repositories import FindingRepository, RunRepository
from metatracer.services.orchestrator import (
    TOTAL_STEPS,
    ProgressEvent,
    ProgressStage,
    ScanOrchestratorService,
    ScanRequest,
)
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

PDF_BYTES = make_pdf_bytes()
JPEG_BYTES = make_jpeg_bytes()

RouteMap = dict[str, tuple[int, str, bytes]]


def _settings(**overrides) -> Settings:
    """Hermetic settings: no .env, no LLM (agent phase = heuristic fallback)."""
    defaults = {
        "rate_limit_rps": 1000.0,  # fast tests; throttling has its own test
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/orchestrator-test.db")
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


async def test_no_scope_confirmation_no_http_no_run(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    """The gate holds before anything else: no HTTP traffic, no Run row."""
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200)

    install_transport(handler)
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(ScopeNotConfirmedError):
        await orchestrator.scan(
            _request(scope_confirmed=False), output_dir=tmp_path
        )
    assert requests == []
    async with session_factory() as session:
        assert await RunRepository(session).list_all() == []


def test_scan_request_requires_targets_and_scope() -> None:
    """At least one target and one scope domain; scope is never inferred."""
    with pytest.raises(ValidationError):
        ScanRequest(targets=[], scope_domains=["target.com"], scope_confirmed=True)
    with pytest.raises(ValidationError):
        ScanRequest(targets=["target.com"], scope_domains=[], scope_confirmed=True)
    with pytest.raises(ValidationError):
        ScanRequest(targets=["   "], scope_domains=["target.com"], scope_confirmed=True)


class _SafetyFailingIngestion:
    """Test double: a safety violation escaping the ingestion stage.

    The real pipeline converts per-asset guard violations into failed assets;
    this double exercises the orchestrator's contract for the exceptions that
    DO escape a stage (ScopeNotConfirmedError / SecurityViolationError).
    """

    async def execute(self, run_id: str) -> NoReturn:
        raise SecurityViolationError("host resolved to a blocked private address")


async def test_safety_error_marks_run_aborted(session_factory, tmp_path) -> None:
    events: list[ProgressEvent] = []
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), ingestion=_SafetyFailingIngestion()
    )
    result = await orchestrator.scan(
        _request(), output_dir=tmp_path, on_progress=events.append
    )

    assert result.status is RunStatus.aborted
    assert result.error_message is not None
    assert "blocked private address" in result.error_message
    assert result.report_paths == {}
    async with session_factory() as session:
        run = await RunRepository(session).get(result.run_id)
    assert run is not None
    assert run.status is RunStatus.aborted
    assert run.error_message is not None and "blocked private address" in run.error_message
    assert run.completed_at is not None
    assert events[-1].stage is ProgressStage.aborted


class _BrokenDetection:
    """Test double: an unexpected (non-safety) stage failure."""

    async def execute(self, run_id: str) -> NoReturn:
        raise RuntimeError("database on fire\nwith a forged second line")


async def test_unexpected_error_marks_run_failed_sanitized(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    events: list[ProgressEvent] = []
    orchestrator = ScanOrchestratorService(
        session_factory, _settings(), detection=_BrokenDetection()
    )
    result = await orchestrator.scan(
        _request(), output_dir=tmp_path, on_progress=events.append
    )

    assert result.status is RunStatus.failed
    assert result.error_message is not None
    assert "RuntimeError" in result.error_message
    # Target-injectable content is sanitized: the forged newline became a space.
    assert "\n" not in result.error_message
    assert events[-1].stage is ProgressStage.failed
    async with session_factory() as session:
        run = await RunRepository(session).get(result.run_id)
    assert run is not None and run.status is RunStatus.failed


async def test_happy_path_completes_with_reports(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    install_transport(
        _routes(
            {
                "/doc.pdf": (200, "application/pdf", PDF_BYTES),
                "/photo.jpg": (200, "image/jpeg", JPEG_BYTES),
            }
        )
    )
    events: list[ProgressEvent] = []
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    result = await orchestrator.scan(
        _request(targets=["http://target.com/doc.pdf", "http://target.com/photo.jpg"]),
        output_dir=tmp_path,
        on_progress=events.append,
    )

    assert result.status is RunStatus.completed
    assert result.error_message is None
    assert result.total_assets == 2
    assert result.total_findings > 0
    assert set(result.report_paths) == {"md", "json", "html", "csv", "bounty"}
    for path in result.report_paths.values():
        assert path.exists()
        assert path.parent == tmp_path
    assert "MetaTracer Security Report" in result.report_paths["md"].read_text(encoding="utf-8")

    async with session_factory() as session:
        run = await RunRepository(session).get(result.run_id)
        findings = await FindingRepository(session).list_by_run(result.run_id)
    assert run is not None
    assert run.status is RunStatus.completed
    assert run.completed_at is not None
    assert run.error_message is None
    assert run.total_assets == 2
    assert run.total_findings == result.total_findings
    # Classification + agent fallback ran: no finding keeps a NULL severity.
    assert findings
    assert all(finding.severity is not None for finding in findings)

    assert events[0].stage is ProgressStage.scope_validation
    assert events[-1].stage is ProgressStage.completed
    assert events[-1].current_step == TOTAL_STEPS
    assert {event.run_id for event in events} == {result.run_id}
    assert all(event.total_steps == TOTAL_STEPS for event in events)
    stages = [event.stage for event in events]
    for expected in (
        ProgressStage.discovery,
        ProgressStage.downloading,
        ProgressStage.extraction,
        ProgressStage.detection,
        ProgressStage.ai_analysis,
        ProgressStage.report_generation,
    ):
        assert expected in stages


async def test_zero_findings_is_a_valid_completed_run(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    html = b"<html><body><p>nothing linked here</p></body></html>"
    install_transport(_routes({"/": (200, "text/html", html)}))
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    result = await orchestrator.scan(
        _request(targets=["http://target.com/"]), output_dir=tmp_path
    )

    assert result.status is RunStatus.completed
    # The HTML page itself is a v1.2 asset; it just has no findings.
    assert result.total_assets == 1
    assert result.total_findings == 0
    assert set(result.report_paths) == {"md", "json", "html", "csv", "bounty"}
    markdown = result.report_paths["md"].read_text(encoding="utf-8")
    assert "No sensitive metadata" in markdown


async def test_second_scan_rejected_while_one_is_running(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    gate = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await gate.wait()
        headers = {
            "content-type": "application/pdf",
            "content-length": str(len(PDF_BYTES)),
        }
        return httpx.Response(200, headers=headers, content=PDF_BYTES)

    install_transport(handler)
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    first = asyncio.create_task(orchestrator.scan(_request(), output_dir=tmp_path))
    for _ in range(100):
        if orchestrator.active_run_id is not None:
            break
        await asyncio.sleep(0.01)
    active_run_id = orchestrator.active_run_id
    assert active_run_id is not None

    with pytest.raises(ScanAlreadyRunningError) as excinfo:
        await orchestrator.scan(_request(), output_dir=tmp_path)
    assert excinfo.value.active_run_id == active_run_id

    gate.set()
    result = await first
    assert result.status is RunStatus.completed
    assert orchestrator.active_run_id is None


async def test_export_report_reexports_persisted_run(
    session_factory, fake_public_dns, install_transport, tmp_path
) -> None:
    install_transport(_routes({"/doc.pdf": (200, "application/pdf", PDF_BYTES)}))
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    result = await orchestrator.scan(_request(), output_dir=tmp_path)
    assert result.status is RunStatus.completed

    other_dir = tmp_path / "reexport"
    paths = await orchestrator.export_report(result.run_id, output_dir=other_dir)
    assert set(paths) == {"md", "json", "html", "csv", "bounty"}
    for path in paths.values():
        assert path.exists()
        assert path.parent == other_dir


async def test_export_report_unknown_run_raises(session_factory, tmp_path) -> None:
    orchestrator = ScanOrchestratorService(session_factory, _settings())
    with pytest.raises(MetaTracerError, match="run not found"):
        await orchestrator.export_report(
            "00000000-0000-0000-0000-000000000000", output_dir=tmp_path
        )
