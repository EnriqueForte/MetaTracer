"""API CRUD for persistent scopes (TASK-10, v2.0).

Reuses the same in-process ASGI setup as test_api_scope.py: lifespan entered
manually, no extra dependency, settings hermetic (tmp db, no LLM).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-scopes-test.db",
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


SCOPE_BODY = {
    "name": "acme-2026",
    "description": "engagement",
    "domains": ["https://Target.COM", "static.example.com"],
}


async def test_create_list_get(client) -> None:
    created = await client.post("/api/scopes", json=SCOPE_BODY)
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "acme-2026"
    # Normalized at write time; Total equals the stored list length.
    assert set(payload["domains"]) == {"target.com", "static.example.com"}
    assert payload["total_domains"] == 2
    scope_id = payload["id"]

    listed = await client.get("/api/scopes")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["scopes"][0]["id"] == scope_id

    detail = await client.get(f"/api/scopes/{scope_id}")
    assert detail.status_code == 200
    assert detail.json()["domains"] == ["target.com", "static.example.com"]


async def test_create_duplicate_name_is_409(client) -> None:
    assert (await client.post("/api/scopes", json=SCOPE_BODY)).status_code == 201
    response = await client.post("/api/scopes", json={**SCOPE_BODY, "domains": ["other.com"]})
    assert response.status_code == 409


async def test_create_validation_422(client) -> None:
    assert (await client.post("/api/scopes", json={**SCOPE_BODY, "domains": []})).status_code == 422
    assert (await client.post("/api/scopes", json={**SCOPE_BODY, "name": "   "})).status_code == 422


async def test_update_replaces_domains(client) -> None:
    created = (await client.post("/api/scopes", json=SCOPE_BODY)).json()
    response = await client.put(
        f"/api/scopes/{created['id']}",
        json={"name": "renamed", "description": None, "domains": ["api.example.com"]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
    assert response.json()["domains"] == ["api.example.com"]


async def test_update_duplicate_name_is_409(client) -> None:
    await client.post("/api/scopes", json=SCOPE_BODY)
    other = (await client.post("/api/scopes", json={**SCOPE_BODY, "name": "other"})).json()
    response = await client.put(
        f"/api/scopes/{other['id']}",
        json={"name": "acme-2026", "description": None, "domains": ["x.com"]},
    )
    assert response.status_code == 409


async def test_update_unknown_scope_404(client) -> None:
    response = await client.put(
        "/api/scopes/00000000-0000-0000-0000-000000000000",
        json={"name": "x", "description": None, "domains": ["x.com"]},
    )
    assert response.status_code == 404


async def test_delete_and_404(client) -> None:
    created = (await client.post("/api/scopes", json=SCOPE_BODY)).json()
    assert (await client.delete(f"/api/scopes/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/scopes/{created['id']}")).status_code == 404
    assert (await client.delete(f"/api/scopes/{created['id']}")).status_code == 404
