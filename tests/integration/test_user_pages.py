"""TASK-25, phase 2 (Web UI): page shells for setup, register, login link
and the users/invitations admin panel.

The shells are tested statically (rendered HTML), following the established
page-test patterns (test_dashboard_page.py, test_history_page.py,
test_a11y_focus.py): data loads client-side from the JSON API, so the suite
asserts the markup contracts (states, alerts, labels) and the page-level
gating (404/redirects), not live JS behavior.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings


def _settings(tmp_path: Path, **overrides) -> Settings:
    values: dict = {
        "_env_file": None,
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/user-pages-test.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }
    values.update(overrides)
    return Settings(**values)


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


@pytest.fixture()
async def auth_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    """Auth ON without METATRACER_AUTH_PASSWORD: setup mode (setup token live)."""
    app = create_app(
        _settings(tmp_path, auth_enabled=True),
        reports_dir=tmp_path / "reports-auth",
    )
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def auth_client(auth_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as client:
        yield client


# --- /setup ---------------------------------------------------------------------


async def test_setup_page_404_with_auth_off(client) -> None:
    response = await client.get("/setup")
    assert response.status_code == 404


async def test_setup_page_404_with_env_password(tmp_path: Path) -> None:
    """Env-provisioned installs permanently disable the setup page (404)."""
    app = create_app(
        _settings(tmp_path / "envpw", auth_enabled=True, auth_password="provisioned-pass-1"),
        reports_dir=(tmp_path / "envpw") / "reports",
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/setup")
    assert response.status_code == 404


async def test_setup_page_redirects_to_login_once_setup_completed(auth_app) -> None:
    """After setup completes (token burned), the page redirects to /login."""
    auth_app.state.setup_token = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/setup")
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


async def test_setup_page_renders_with_live_setup_token(auth_client) -> None:
    response = await auth_client.get("/setup")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Initial setup" in response.text
    assert "/api/auth/setup" in response.text
    # Form contract: labeled fields, password-type token input, hint.
    assert 'for="setup_token"' in response.text
    assert 'type="password"' in response.text
    assert "Minimum 8 characters" in response.text
    assert 'role="alert"' in response.text


# --- /register ------------------------------------------------------------------


async def test_register_page_404_with_auth_off(client) -> None:
    response = await client.get("/register")
    assert response.status_code == 404


async def test_register_page_renders_with_auth_on(auth_client) -> None:
    response = await auth_client.get("/register")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Create your account" in response.text
    assert "/api/auth/register" in response.text
    assert 'for="code"' in response.text
    # Generic 401 message only: the page never reveals code state upfront.
    assert "Invalid, used or expired invitation code." in response.text
    assert 'href="/login"' in response.text
    assert 'role="alert"' in response.text


# --- /login cross-link ------------------------------------------------------------


async def test_login_page_links_to_register_with_auth_on(auth_client) -> None:
    response = await auth_client.get("/login")
    assert response.status_code == 200
    assert 'href="/register"' in response.text
    assert "Have an invitation code?" in response.text


# --- /users admin panel -----------------------------------------------------------


@asynccontextmanager
async def _operator_session(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Complete setup against the app and yield a logged-in client.

    The setup POST is pre-session CSRF-protected: the GET /setup render issues
    the throwaway csrf_token cookie first, which the POST echoes in the header.
    """
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    try:
        await client.get("/setup")  # issues the pre-session CSRF cookie
        csrf = client.cookies.get("csrf_token", "")
        token = app.state.setup_token
        response = await client.post(
            "/api/auth/setup",
            json={
                "setup_token": token,
                "username": "admin",
                "password": "admin-pass-123",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        yield client
    finally:
        await client.aclose()


async def test_users_page_renders_shell(auth_app) -> None:
    async with _operator_session(auth_app) as client:
        response = await client.get("/users")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Users &amp; invitations" in response.text
        assert "/api/users" in response.text
        assert "/api/invitations" in response.text
        # Data-state shells: loading, empty, error + Retry.
        assert "Loading users" in response.text
        assert "No invitations yet" in response.text
        assert "Retry" in response.text
        # Viewer posture message and 409 messages ship in the markup.
        assert "Operator role required" in response.text
        assert "Cannot remove the last operator" in response.text
        # The one-shot code banner exists but renders empty by default.
        assert "This code will not be shown again." in response.text
        # Mutation fetches always go through the CSRF-aware wrapper.
        assert "authFetch" in response.text
        # Delete confirmation uses the repo's native-confirm pattern.
        assert "window.confirm" in response.text
        # The operator sees the Users nav link and the signed-in header.
        assert 'href="/users"' in response.text
        assert "Signed in as" in response.text
        assert "admin" in response.text


async def test_users_page_viewer_nav_hides_users_link(auth_app) -> None:
    """A viewer session renders the shell but never the Users nav link."""
    async with _operator_session(auth_app) as operator:
        csrf = operator.cookies.get("csrf_token", "")
        response = await operator.post(
            "/api/invitations",
            json={"role": "viewer"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
        code = response.json()["code"]
        viewer = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=auth_app), base_url="http://testserver"
        )
        try:
            await viewer.get("/register")  # issues the pre-session CSRF cookie
            register = await viewer.post(
                "/api/auth/register",
                json={
                    "code": code,
                    "username": "watcher",
                    "password": "viewer-pass-123",
                },
                headers={"X-CSRF-Token": viewer.cookies.get("csrf_token", "")},
            )
            assert register.status_code == 200
            page = await viewer.get("/users")
            assert page.status_code == 200
            assert "Operator role required" in page.text
            assert 'href="/users"' not in page.text  # nav link hidden for viewers
            assert "Signed in as" in page.text
        finally:
            await viewer.aclose()


async def test_users_page_no_longer_bounces_anonymous_to_login(auth_client) -> None:
    """T11 cut-over: the HTML-page redirect is gone with Web V1.

    FastAPI no longer renders browser pages, so there is nothing to redirect.
    Web V2 (Next.js) owns that surface and sends the anonymous visitor to
    /login client-side. The API itself still answers 401 JSON.
    """
    response = await auth_client.get("/users")
    # T11a: pages_router is still mounted; T11b removes it and this becomes 404.
    assert response.status_code != 307
    runs = await auth_client.get("/api/runs")
    assert runs.status_code == 401  # the authority is the API, not the page


async def test_users_page_auth_off_renders_permissive_shell(client) -> None:
    """With auth OFF the page is anonymous-permissive (like the rest of the
    UI): the shell renders and the page JS answers everything via API."""
    response = await client.get("/users")
    assert response.status_code == 200
    assert "/api/users" in response.text


# --- accessibility contracts --------------------------------------------------------


async def test_new_forms_have_labels_and_alerts(auth_client) -> None:
    """Every new form control has a <label for>; error blocks use role=alert."""
    setup_html = (await auth_client.get("/setup")).text
    register_html = (await auth_client.get("/register")).text
    for html in (setup_html, register_html):
        assert "<label for=" in html
        assert 'role="alert"' in html
    for field in ("setup_token", "username", "password"):
        assert f'for="{field}"' in setup_html
    for field in ("code", "username", "password"):
        assert f'for="{field}"' in register_html


async def test_users_page_uses_base_layout_a11y(auth_app) -> None:
    """users.html extends base.html: skip-link, labeled nav and ARIA survive."""
    async with _operator_session(auth_app) as client:
        html = (await client.get("/users")).text
        assert "Skip to main content" in html
        assert 'id="main-content"' in html
        assert 'aria-label="Primary"' in html
        assert 'aria-label="Admin sections"' in html
        assert 'role="tab"' in html


async def test_users_nav_link_operator_only(auth_client) -> None:
    """Pre-session pages (login) render no nav chrome at all — the Users link
    must not leak into them; viewer visibility is locked separately."""
    anonymous = await auth_client.get("/login")
    assert 'href="/users"' not in anonymous.text  # pre-session: no nav chrome
