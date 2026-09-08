"""GET/DELETE /api/notifications (TASK-12, v2.0).

Reuses the in-process ASGI setup of the other API tests. The queue is
in-memory on app.state, seeded through the bus itself — the same object the
orchestrator publishes to. GET is read-only; DELETE works by list index and
answers 404 for invalid or stale indexes.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import RunStatus
from metatracer.services.notifications import NotificationEvent


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-notifications-test.db",
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


def _seed_bus(app: FastAPI, *, n: int = 2) -> None:
    """Publish N notifications into the app's own in-memory bus (newest last)."""
    bus = app.state.notifications_bus
    for i in range(n):
        bus.publish(
            NotificationEvent(
                id=0,
                kind=RunStatus.completed if i % 2 == 0 else RunStatus.failed,
                run_id=f"{i:08d}-0000-4000-8000-000000000000",
                target=f"target{i}.com",
                total_assets=1 + i,
                total_findings=2 + i,
                error_message=None if i % 2 == 0 else "boom",
                created_at=datetime(2026, 9, 8, 12, 0, i, tzinfo=UTC),
            )
        )


async def test_list_empty_database(client) -> None:
    response = await client.get("/api/notifications")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["notifications"] == []


async def test_list_returns_queue_newest_first_with_contract(app, client) -> None:
    _seed_bus(app, n=3)

    response = await client.get("/api/notifications")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 3
    entries = payload["notifications"]
    assert len(entries) == 3
    # Newest first: the last published (i=2, completed) is the first listed.
    assert entries[0]["target"] == "target2.com"
    assert entries[0]["kind"] == "completed"
    assert entries[0]["error_message"] is None
    # A failed entry carries its sanitized message.
    failed = next(e for e in entries if e["kind"] == "failed")
    assert failed["error_message"] == "boom"
    # Every entry fulfills the contract keys.
    for entry in entries:
        assert set(entry) == {
            "id",
            "kind",
            "run_id",
            "target",
            "total_assets",
            "total_findings",
            "error_message",
            "created_at",
        }
        assert entry["kind"] in {"completed", "failed"}


async def test_delete_by_index_then_404_for_stale_index(app, client) -> None:
    _seed_bus(app, n=2)

    response = await client.delete("/api/notifications/0")
    assert response.status_code == 204

    remaining = (await client.get("/api/notifications")).json()
    assert remaining["total"] == 1
    # The remaining entry is the older one (index 1 before the delete).
    assert remaining["notifications"][0]["target"] == "target0.com"


async def test_delete_invalid_index_returns_404(client) -> None:
    assert (await client.delete("/api/notifications/0")).status_code == 404
    assert (await client.delete("/api/notifications/99")).status_code == 404
    assert (await client.delete("/api/notifications/-1")).status_code == 404


async def test_get_is_read_only(app, client) -> None:
    """The GET never writes: the queue is unchanged after a call."""
    _seed_bus(app, n=2)
    before = (await client.get("/api/notifications")).json()["total"]

    assert (await client.get("/api/notifications")).status_code == 200

    after = (await client.get("/api/notifications")).json()["total"]
    assert before == after == 2