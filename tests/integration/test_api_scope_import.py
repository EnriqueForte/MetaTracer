"""POST /api/scopes/import (TASK-19, v2.2): portable scopes over the API."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.repositories import ScopeRepository

_VALID = {
    "format_version": 1,
    "scopes": [
        {
            "name": "acme-2026",
            "description": "Acme Corp engagement",
            "domains": ["target.com", "*.target.com", "static.Target.com:8080"],
        },
        {"name": "other-2026", "description": None, "domains": ["api.other.com"]},
    ],
}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-scope-import-test.db",
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


async def _count(app: FastAPI) -> int:
    async with app.state.session_factory() as session:
        return len(await ScopeRepository(session).list_all())


async def test_import_inserts_and_responds_counts(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    response = await client.post(
        "/api/scopes/import", content=json.dumps(_VALID).encode("utf-8")
    )
    assert response.status_code == 201
    assert response.json() == {"imported": 2, "skipped": 0}
    assert await _count(app) == 2

    # The imported scope is usable just like a hand-created one.
    async with app.state.session_factory() as session:
        scope = await ScopeRepository(session).get_by_name("acme-2026")
    assert scope is not None
    assert json.loads(scope.domains) == ["target.com", "*.target.com", "static.target.com"]


async def test_import_is_idempotent_via_api(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    body = json.dumps(_VALID).encode("utf-8")
    r1 = await client.post("/api/scopes/import", content=body)
    r2 = await client.post("/api/scopes/import", content=body)
    assert r1.status_code == 201
    assert r1.json() == {"imported": 2, "skipped": 0}
    assert r2.status_code == 201
    assert r2.json() == {"imported": 0, "skipped": 2}
    assert await _count(app) == 2


async def test_import_invalid_file_is_422(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    bad = {"format_version": 99, "scopes": []}
    response = await client.post(
        "/api/scopes/import", content=json.dumps(bad).encode("utf-8")
    )
    assert response.status_code == 422
    assert "format_version" in response.json()["detail"].lower()
    assert await _count(app) == 0


async def test_import_without_body_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/scopes/import")
    assert response.status_code == 422