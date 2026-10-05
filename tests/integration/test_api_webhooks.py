"""Integration tests for the webhook CRUD API (TASK-15, v2.2).

Contract verified:

- POST creates a config (HTTPS required; HTTP and non-terminal events → 422);
- GET lists configs with header values redacted and never the secret hash;
- PUT updates fields and 404s on unknown id;
- DELETE removes the config and 204/404s;
- GET /webhooks/{id}/deliveries lists persisted relay-buffer rows or 404.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import Run, WebhookConfig
from metatracer.db.repositories import RunRepository, WebhookConfigRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-webhooks-test.db",
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


async def _seed_webhook(app: FastAPI, **kw) -> WebhookConfig:
    async with app.state.session_factory() as session:
        return await WebhookConfigRepository(session).create(
            WebhookConfig(url="https://hooks.example.com/wh", **kw)
        )


async def _seed_run(app: FastAPI, **kw) -> Run:
    async with app.state.session_factory() as session:
        return await RunRepository(session).create(
            Run(
                target_input='["t.com"]',
                allowed_scope='["t.com"]',
                scope_confirmed=True,
                status="completed",
                **kw,
            )
        )


async def test_post_get_update_delete_flow(app: FastAPI, client) -> None:
    response = await client.post(
        "/api/webhooks",
        json={
            "url": "https://hooks.example.com/wh",
            "name": "alerts",
            "event": "completed",
            "headers": {"X-Token": "s3cr3t"},
            "signature_secret": "supersecret",
            "max_retries": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    webhook_id = body["id"]
    assert body["url"] == "https://hooks.example.com/wh"
    assert body["headers"] == {"X-Token": "***"}
    assert body["signature_status"] == "active"
    assert "signature_secret" not in body
    assert "signature_secret_hash" not in body
    assert "supersecret" not in response.text

    async with app.state.session_factory() as session:
        stored = await WebhookConfigRepository(session).get(webhook_id)
    assert stored is not None
    assert stored.signature_secret == "supersecret"
    assert stored.signature_secret_hash

    listed = await client.get("/api/webhooks")
    assert listed.status_code == 200
    assert any(item["id"] == webhook_id for item in listed.json())

    updated = await client.put(
        f"/api/webhooks/{webhook_id}",
        json={"name": "renamed", "active": False, "max_retries": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed"
    assert updated.json()["active"] is False
    assert updated.json()["max_retries"] == 2

    deleted = await client.delete(f"/api/webhooks/{webhook_id}")
    assert deleted.status_code == 204
    assert (await client.delete(f"/api/webhooks/{webhook_id}")).status_code == 404


async def test_post_rejects_http_url(app: FastAPI, client) -> None:
    response = await client.post(
        "/api/webhooks",
        json={"url": "http://hooks.example.com/wh"},
    )
    assert response.status_code == 422


async def test_post_rejects_non_terminal_event(app: FastAPI, client) -> None:
    response = await client.post(
        "/api/webhooks",
        json={"url": "https://hooks.example.com/wh", "event": "running"},
    )
    assert response.status_code == 422


async def test_put_unknown_is_404(app: FastAPI, client) -> None:
    response = await client.put(
        "/api/webhooks/00000000-0000-4000-8000-000000000000",
        json={"name": "x"},
    )
    assert response.status_code == 404


async def test_deliveries_listing_and_404(app: FastAPI, client) -> None:
    run = await _seed_run(app)
    webhook = await _seed_webhook(app, name="deliveries")
    # Persist one relay-buffer row directly so the listing has data.
    from metatracer.db.models import WebhookDelivery, WebhookDeliveryStatus
    from metatracer.db.repositories import WebhookDeliveryRepository

    async with app.state.session_factory() as session:
        await WebhookDeliveryRepository(session).create(
            WebhookDelivery(
                webhook_id=webhook.id,
                run_id=run.id,
                status=WebhookDeliveryStatus.pending,
                payload_json="{}",
            )
        )

    response = await client.get(f"/api/webhooks/{webhook.id}/deliveries")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["run_id"] == run.id
    assert rows[0]["status"] == "pending"

    missing = await client.get(
        "/api/webhooks/00000000-0000-4000-8000-000000000000/deliveries"
    )
    assert missing.status_code == 404