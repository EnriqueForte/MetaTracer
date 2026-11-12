"""Integration tests for the auth surface (TASK-24, Eje C).

Real ASGI app (httpx.ASGITransport + lifespan) with auth_enabled=True unless
stated: 401 without cookie, 401 with expired/unknown session, 403 CSRF,
403 viewer on mutations, full login/logout/me flows, and the kill-switch
(auth disabled == v0.5.0 behavior).
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings
from metatracer.db.models import User, UserRole, UserSession


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/auth-test.db",
        "rate_limit_rps": 1000.0,
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "auth_enabled": True,
        "auth_password": "test-password-123",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(
        _settings(tmp_path, auth_password="test-password-123"),
        reports_dir=tmp_path / "reports",
    )
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _login(
    client: httpx.AsyncClient,
    username: str = "operator",
    password: str = "test-password-123",
) -> dict:
    """Login flow as the UI does it: GET /login first (issues the throwaway
    pre-session CSRF cookie), then POST credentials with the header."""
    page = await client.get("/api/auth/me")
    # Signed out answers 401, but the pre-session CSRF token is issued.
    assert page.status_code in (200, 401)
    csrf = client.cookies.get("csrf_token", "")
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _login_as_viewer(client: httpx.AsyncClient) -> dict:
    """Create a viewer user directly in the DB, then log in as it."""
    session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
    from metatracer.api.auth import hash_password

    async with session_factory() as db:
        db.add(
            User(
                username="viewer",
                password_hash=hash_password("viewer-password-123"),
                role=UserRole.viewer,
            )
        )
        await db.commit()
    return await _login(client, username="viewer", password="viewer-password-123")


class TestAuthDisabledKillSwitch:
    async def test_disabled_allows_everything_like_v050(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_enabled=False), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                health = await client.get("/api/health")
                assert health.status_code == 200
                runs = await client.get("/api/runs")
                assert runs.status_code == 200


class TestLoginPage:

    async def test_pages_no_longer_redirect_to_login_without_session(
        self, client: httpx.AsyncClient
    ):
        """T11: the HTML-page redirect died with Web V1.

        There is no server-rendered page to bounce; Web V2 (Next.js) handles
        the signed-out redirect. The API keeps answering 401.
        """
        response = await client.get("/", follow_redirects=False)
        assert response.status_code != 307
        runs = await client.get("/api/runs")
        assert runs.status_code == 401

    async def test_data_api_401_without_session(self, client: httpx.AsyncClient):
        for path in ("/api/runs", "/api/scopes", "/api/stats", "/api/notifications"):
            response = await client.get(path)
            assert response.status_code == 401, path
        health = await client.get("/api/health")
        assert health.status_code == 200  # exempt


class TestLoginFlow:
    async def test_login_sets_cookies_and_rotates_sessions(
        self, client: httpx.AsyncClient, tmp_path: Path
    ):
        first = await _login(client)
        assert first["role"] == "operator"
        cookies = dict(client.cookies)
        assert "metatracer_session" in cookies
        assert "csrf_token" in cookies
        first_session = cookies["metatracer_session"]

        second = await _login(client)
        assert second["role"] == "operator"
        assert dict(client.cookies)["metatracer_session"] != first_session

        # Exactly one session row survives (rotation).
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
        from sqlmodel import select

        from metatracer.db.models import UserSession as UserSessionModel

        async with session_factory() as db:
            rows = (await db.exec(select(UserSessionModel))).all()
        assert len(rows) == 1

    async def test_login_rejects_wrong_password(self, client: httpx.AsyncClient):
        await client.get("/api/auth/me")  # issue pre-session CSRF cookie
        response = await client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "wrong-password"},
            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")},
        )
        assert response.status_code == 401

    async def test_me_issues_pre_session_csrf_when_cookie_missing(
        self, client: httpx.AsyncClient
    ):
        client.cookies.clear()
        response = await client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.cookies.get("csrf_token")

    async def test_login_without_csrf_is_403(self, client: httpx.AsyncClient):
        await client.get("/api/auth/me")  # cookie set, but no header sent
        response = await client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "test-password-123"},
        )
        assert response.status_code == 403

    async def test_login_unknown_username_same_status(self, client: httpx.AsyncClient):
        await client.get("/api/auth/me")
        response = await client.post(
            "/api/auth/login",
            json={"username": "who-dis", "password": "whatever-thing"},
            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")},
        )
        assert response.status_code == 401

    async def test_me_reports_user(self, client: httpx.AsyncClient):
        await _login(client)
        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["authenticated"] is True
        assert body["username"] == "operator"
        assert body["role"] == "operator"
        # The session token (HttpOnly) and password hash must never leave the
        # server; the CSRF token is deliberately non-HttpOnly and is exposed
        # so Web V2 can echo it back on mutations (MIN-01 parity).
        assert "password_hash" not in me.text.lower()
        assert "metatracer_session" not in me.text.lower()
        assert body["csrf_token"]

    async def test_me_returns_csrf_token_while_signed_out(self, client: httpx.AsyncClient):
        """Web V2 bootstraps the pre-session CSRF from GET /me even when 401."""
        client.cookies.clear()
        response = await client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.headers["x-csrf-token"]
        assert response.cookies.get("csrf_token")
        assert response.headers["x-csrf-token"] == response.cookies.get("csrf_token")

    async def test_logout_invalidates_session(self, client: httpx.AsyncClient):
        payload = await _login(client)
        logout = await client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert logout.status_code == 200
        after = await client.get("/api/runs")
        assert after.status_code == 401

    async def test_logout_without_csrf_is_403(self, client: httpx.AsyncClient):
        await _login(client)
        logout = await client.post("/api/auth/logout")
        assert logout.status_code == 403


class TestCsrfAndRoles:
    async def test_mutation_without_csrf_is_403(self, client: httpx.AsyncClient):
        await _login(client)
        response = await client.post(
            "/api/scopes",
            json={"name": "s", "domains": ["target.com"]},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    async def test_mutation_with_bad_csrf_is_403(self, client: httpx.AsyncClient):
        await _login(client)
        response = await client.post(
            "/api/scopes",
            json={"name": "s", "domains": ["target.com"]},
            headers={"X-CSRF-Token": "forged-token"},
        )
        assert response.status_code == 403

    async def test_operator_can_mutate_with_csrf(self, client: httpx.AsyncClient):
        payload = await _login(client)
        csrf = payload["csrf_token"]
        response = await client.post(
            "/api/scopes",
            json={"name": "engagement-1", "domains": ["target.com"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201, response.text

    async def test_viewer_reads_ok_but_cannot_mutate(
        self, client: httpx.AsyncClient
    ):
        payload = await _login_as_viewer(client)
        csrf = payload["csrf_token"]
        assert payload["role"] == "viewer"

        reads = [
            await client.get("/api/runs"),
            await client.get("/api/scopes"),
            await client.get("/api/stats"),
            await client.get("/api/notifications"),
            await client.get("/api/search", params={"q": "test"}),
        ]
        statuses = {r.status_code for r in reads}
        assert statuses == {200}, f"viewer reads failed: {statuses}"

        denied = await client.post(
            "/api/scopes",
            json={"name": "s", "domains": ["target.com"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert denied.status_code == 403
        assert "operator" in denied.json()["detail"]

    async def test_expired_session_is_401(self, client: httpx.AsyncClient):
        await _login(client)
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
        # Force-expire the session server-side (the cookie alone must not pass).
        from sqlmodel import update

        async with session_factory() as db:
            await db.exec(
                update(UserSession)
                .values(expires_at=_utc_now() - timedelta(seconds=1))
            )
            await db.commit()
        response = await client.get("/api/runs")
        assert response.status_code == 401

    async def test_db_leak_does_not_yield_valid_cookie(
        self, client: httpx.AsyncClient, tmp_path: Path
    ):
        """The stored token hash must not authenticate by itself."""
        await _login(client)
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
        from sqlmodel import select

        async with session_factory() as db:
            row = (await db.exec(select(UserSession))).first()
        # Replay the HASH as if it were the cookie: must fail (only the
        # pre-hash token works — sha256 stored, token never persisted).
        client.cookies.set("metatracer_session", row.token_hash)
        response = await client.get("/api/runs")
        assert response.status_code == 401

    async def test_scoped_flow_still_enforced_for_operator(
        self, client: httpx.AsyncClient, tmp_path: Path
    ):
        """Auth does not weaken the safety core: unconfirmed scope still 403."""
        payload = await _login(client)
        response = await client.post(
            "/api/runs",
            json={
                "targets": ["http://target.com/doc.pdf"],
                "scope_domains": ["target.com"],
                "scope_confirmed": False,
                "reasoning_depth": "standard",
            },
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 403


class TestWebhookAuth:
    """The webhook CRUD is the most sensitive surface (review HIGH finding):
    an unauthenticated caller must never be able to create/modify webhooks."""

    async def test_webhooks_401_without_session(self, client: httpx.AsyncClient):
        for method, path in (
            ("GET", "/api/webhooks"),
            ("POST", "/api/webhooks"),
            ("PUT", "/api/webhooks/xyz"),
            ("DELETE", "/api/webhooks/xyz"),
            ("GET", "/api/webhooks/xyz/deliveries"),
        ):
            response = await client.request(
                method, path, json={"name": "n", "url": "https://exfil.example/hook"}
            )
            assert response.status_code == 401, f"{method} {path}: {response.status_code}"

    async def test_webhooks_403_without_csrf(self, client: httpx.AsyncClient):
        await _login(client)
        response = await client.post(
            "/api/webhooks",
            json={
                "name": "sneaky",
                "url": "https://exfil.example/hook",
                "event": "completed",
            },
        )
        assert response.status_code == 403

    async def test_operator_can_create_webhook_with_csrf(
        self, client: httpx.AsyncClient
    ):
        payload = await _login(client)
        response = await client.post(
            "/api/webhooks",
            json={
                "name": "ops-hook",
                "url": "https://hooks.example/metatracer",
                "event": "completed",
            },
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "ops-hook"


def _utc_now():
    from metatracer.api.auth import _utc_now as auth_utc_now

    return auth_utc_now()
