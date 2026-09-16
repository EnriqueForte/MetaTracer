"""API scope-gate and contract tests (TASK-06, subtask 6.3).

The app runs in-process over httpx.ASGITransport with the lifespan entered
manually (no extra test dependency). DNS and the pipeline's HTTP transport are
faked; ScopeValidator and NetworkSafetyGuard are the real ones. Settings carry
no LLM configuration, so the agent phase degrades to the heuristic fallback.

Fixture order matters: the API ``client`` (ASGI transport) is created BEFORE
``install_transport`` patches ``httpx.AsyncClient``, so only the pipeline's
clients get the mock transport.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.repositories import RunRepository
from tests.fixtures.builders import make_jpeg_bytes, make_pdf_bytes

PDF_BYTES = make_pdf_bytes()
JPEG_BYTES = make_jpeg_bytes()

VALID_BODY = {
    "targets": ["http://target.com/doc.pdf"],
    "scope_domains": ["target.com"],
    "scope_confirmed": True,
    "reasoning_depth": "standard",
}


def _settings(tmp_path: Path, **overrides) -> Settings:
    """Hermetic settings: tmp database, no .env, no LLM (heuristic fallback)."""
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/api-test.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


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


def _routes(routes: dict[str, tuple[int, str, bytes]]):
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


async def _wait_for_status(
    client: httpx.AsyncClient, run_id: str, want: str, timeout: float = 20.0
) -> dict:
    """Poll GET /api/runs/{id} until the run reaches the wanted status."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == want:
            return payload
        if loop.time() > deadline:
            pytest.fail(f"run {run_id} did not reach {want} (last: {payload['status']})")
        await asyncio.sleep(0.05)


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            pytest.fail("condition not met within the timeout")
        await asyncio.sleep(0.02)


async def test_post_run_without_scope_confirmation_is_403(client, app) -> None:
    response = await client.post("/api/runs", json={**VALID_BODY, "scope_confirmed": False})
    assert response.status_code == 403
    # The gate held before anything else: no Run row was persisted.
    async with app.state.session_factory() as session:
        assert await RunRepository(session).list_all() == []


async def test_post_run_validation_error_is_422(client) -> None:
    response = await client.post("/api/runs", json={**VALID_BODY, "scope_domains": []})
    assert response.status_code == 422


async def test_get_run_404(client) -> None:
    response = await client.get("/api/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_health_endpoint(client) -> None:
    """Liveness probe for the Docker HEALTHCHECK (TASK-07, subtask 7.3.5)."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_findings_severity_filter_validation(client) -> None:
    # Invalid enum value: 422 before the run is even looked up.
    response = await client.get("/api/runs/whatever/findings", params={"severity": "bogus"})
    assert response.status_code == 422
    # Valid filter on an unknown run: 404.
    response = await client.get("/api/runs/whatever/findings", params={"severity": "high"})
    assert response.status_code == 404


async def test_export_unknown_run_404(client) -> None:
    response = await client.get(
        "/api/runs/00000000-0000-0000-0000-000000000000/export", params={"format": "md"}
    )
    assert response.status_code == 404


async def test_list_runs_empty(client) -> None:
    response = await client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "runs": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_history_page_renders(client) -> None:
    response = await client.get("/runs")
    assert response.status_code == 200
    assert "Local history" in response.text


async def test_index_page_renders(client) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MetaTracer" in response.text
    # The blocking scope modal is part of the wizard.
    assert "Confirm authorized scope" in response.text


async def test_run_page_shell_renders(client) -> None:
    response = await client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


async def test_happy_path_scan_findings_export_and_stream(
    client, app, fake_public_dns, install_transport
) -> None:
    install_transport(
        _routes(
            {
                "/doc.pdf": (200, "application/pdf", PDF_BYTES),
                "/photo.jpg": (200, "image/jpeg", JPEG_BYTES),
            }
        )
    )
    body = {
        **VALID_BODY,
        "targets": ["http://target.com/doc.pdf", "http://target.com/photo.jpg"],
    }
    response = await client.post("/api/runs", json=body)
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    run = await _wait_for_status(client, run_id, "completed")
    assert run["total_assets"] == 2
    assert run["total_findings"] > 0
    assert run["error_message"] is None
    assert run["target"] == "http://target.com/doc.pdf"
    assert run["scope"] == ["target.com"]
    assert run["reasoning_depth"] == "standard"
    assert run["completed_at"] is not None
    assert run["asset_issues"] == []

    # Findings: report order (critical -> info), lowercase enums on the wire.
    response = await client.get(f"/api/runs/{run_id}/findings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == run["total_findings"]
    ranks = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1, None: 0}
    severities = [finding["severity"] for finding in payload["findings"]]
    assert [ranks[s] for s in severities] == sorted(
        (ranks[s] for s in severities), reverse=True
    )
    first = payload["findings"][0]
    for key in (
        "id",
        "finding_type",
        "severity",
        "confidence",
        "field_source",
        "evidence_snippet",
        "severity_justification",
        "impact_analysis",
        "remediation_advice",
        "reproduction_steps",
        "asset_source_url",
        "asset_final_url",
        "asset_content_type",
    ):
        assert key in first

    # Severity filter returns a consistent subset.
    top = severities[0]
    response = await client.get(f"/api/runs/{run_id}/findings", params={"severity": top})
    assert response.status_code == 200
    filtered = response.json()
    assert filtered["total"] >= 1
    assert all(f["severity"] == top for f in filtered["findings"])

    # Export: attachment with the exporter's sanitized file name, both formats.
    response = await client.get(f"/api/runs/{run_id}/export", params={"format": "md"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "metatracer-" in response.headers["content-disposition"]
    assert "MetaTracer Security Report" in response.text
    response = await client.get(f"/api/runs/{run_id}/export", params={"format": "json"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert json.loads(response.text)["run_id"] == run_id
    response = await client.get(f"/api/runs/{run_id}/export", params={"format": "html"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "MetaTracer Security Report" in response.text
    assert "<script>" not in response.text
    # TASK-18: CSV and bounty (plain text) are downloadable too.
    response = await client.get(f"/api/runs/{run_id}/export", params={"format": "csv"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-type"].startswith("text/csv")
    assert "severity,finding_type,confidence" in response.text
    response = await client.get(f"/api/runs/{run_id}/export", params={"format": "bounty"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-type"].startswith("text/plain")
    assert "=== Finding 1/" in response.text

    listed = await client.get("/api/runs")
    assert listed.status_code == 200
    history = listed.json()
    assert history["total"] == 1
    assert history["runs"][0]["run_id"] == run_id
    assert history["runs"][0]["status"] == "completed"

    first_type = first["finding_type"]
    typed = await client.get(
        f"/api/runs/{run_id}/findings", params={"finding_type": first_type}
    )
    assert typed.status_code == 200
    assert typed.json()["total"] >= 1
    assert all(item["finding_type"] == first_type for item in typed.json()["findings"])

    # SSE replay after completion: full history, terminal event closes.
    events = []
    async with asyncio.timeout(10):
        async with client.stream("GET", f"/api/runs/{run_id}/stream") as stream:
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
    assert events[0]["stage"] == "scope_validation"
    assert events[-1]["stage"] == "completed"
    assert all(event["run_id"] == run_id for event in events)


async def test_second_post_returns_409(client, app, fake_public_dns, install_transport) -> None:
    gate = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await gate.wait()
        headers = {
            "content-type": "application/pdf",
            "content-length": str(len(PDF_BYTES)),
        }
        return httpx.Response(200, headers=headers, content=PDF_BYTES)

    install_transport(handler)
    response = await client.post("/api/runs", json=VALID_BODY)
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    await _wait_for(lambda: app.state.orchestrator.active_run_id is not None)
    response = await client.post("/api/runs", json=VALID_BODY)
    assert response.status_code == 409

    gate.set()
    run = await _wait_for_status(client, run_id, "completed")
    assert run["run_id"] == run_id
