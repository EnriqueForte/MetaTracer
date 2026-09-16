"""Scan integration with a saved scope (TASK-10, 10.4).

POST /api/scopes -> POST /api/runs {scope_id} resolves the allowed_scope from
the saved scope; scope_id + scope_domains together is ambiguous (422); an
unknown scope_id is a 404; deleting the scope after the run leaves the run
intact (the run owns its scope snapshot).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.repositories import RunRepository


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/api-scope-scan-test.db",
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


async def _create_scope(client: httpx.AsyncClient, name: str = "acme") -> dict:
    response = await client.post(
        "/api/scopes",
        json={"name": name, "description": "e2e", "domains": ["target.com"]},
    )
    assert response.status_code == 201
    return response.json()


async def test_scope_id_resolves_allowed_scope_on_run(app, client) -> None:
    scope = await _create_scope(client)
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_id": scope["id"],
            "scope_confirmed": True,
            "reasoning_depth": "standard",
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    # The Run row persists the resolved domains, not a reference to the scope.
    async with app.state.session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.allowed_scope == '["target.com"]'
    assert run.scope_confirmed is True


async def test_scope_id_and_scope_domains_together_is_422(client) -> None:
    scope = await _create_scope(client)
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_id": scope["id"],
            "scope_domains": ["other.com"],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 422


async def test_unknown_scope_id_is_404(client) -> None:
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_id": "00000000-0000-0000-0000-000000000000",
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 404


async def test_deleting_scope_after_run_leaves_run_intact(app, client) -> None:
    scope = await _create_scope(client)
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_id": scope["id"],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    assert (await client.delete(f"/api/scopes/{scope['id']}")).status_code == 204

    async with app.state.session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.allowed_scope == '["target.com"]'


async def test_scope_ids_union_resolves_deduplicated_allowed_scope(app, client) -> None:
    """TASK-21 (v2.4): several saved scopes become one deduplicated union."""
    first = await _create_scope(client, name="acme")
    await client.post(
        "/api/scopes",
        json={
            "name": "acme-cdn",
            "description": "e2e",
            "domains": ["cdn.acme.com", "target.com"],  # target.com already in first
        },
    )
    second = (await client.get("/api/scopes")).json()
    second = next(s for s in second["scopes"] if s["name"] == "acme-cdn")

    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_ids": [first["id"], second["id"]],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    # The snapshot holds the stable union, deduplicated, normalized order.
    async with app.state.session_factory() as session:
        run = await RunRepository(session).get(run_id)
    assert run is not None
    assert run.allowed_scope == '["target.com", "cdn.acme.com"]'


async def test_scope_ids_unknown_id_is_404_with_name(app, client) -> None:
    """TASK-21 (v2.4): an unknown id in the union aborts before any row."""
    known = await _create_scope(client, name="acme")
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_ids": [known["id"], "00000000-0000-0000-0000-000000000000"],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 404
    assert "scope not found" in response.json()["detail"]


async def test_scope_ids_and_scope_domains_together_is_422(client) -> None:
    """TASK-21 (v2.4): mixing scope sources is rejected by the contract."""
    first = await _create_scope(client, name="acme")
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_ids": [first["id"]],
            "scope_domains": ["other.com"],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 422


async def test_scope_ids_empty_is_422(client) -> None:
    """TASK-21 (v2.4): an empty union is not a scope source."""
    response = await client.post(
        "/api/runs",
        json={
            "targets": ["http://target.com/doc.pdf"],
            "scope_ids": [],
            "scope_confirmed": True,
        },
    )
    assert response.status_code == 422


async def test_wizard_shell_supports_multi_scope(client) -> None:
    """TASK-21 (v2.4): the wizard ships the multi-select wired to scope_ids."""
    response = await client.get("/")
    assert response.status_code == 200
    html = response.text
    # The saved-scope multi-selector renders checkboxes over /api/scopes.
    assert "selectedScopeIds" in html
    assert "scope_ids" in html
    # The manual fallback (v1.x wire contract) stays present.
    assert "scope_domains" in html
    # The scope is never inferred: the empty-scope guard message is in the shell.
    assert "the scope is never inferred from the target" in html


async def test_wizard_manual_scope_field_does_not_block_saved_scopes(client) -> None:
    """TASK-22 (v3.0 Eje A, bug UX): picking a saved scope must not force the
    manual domain input. Browser-native ``required`` would block the submit
    before Alpine's own validation (which accepts saved scopes), so the
    manual input must NOT carry the ``required`` attribute anymore."""
    response = await client.get("/")
    assert response.status_code == 200
    html = response.text
    # The visible manual input no longer forces a value when saved scopes
    # are the chosen source.
    assert 'id="scope" type="text" x-model="scopeDomains"' in html.replace("\n", "")
    # Neither the visible input nor the <details> fallback carries `required`.
    assert 'x-model="scopeDomains" required' not in html
    # The unique-id refactor: the manual fallback input is not a duplicate id.
    assert html.count('id="scope"') == 1