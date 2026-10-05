"""Integration tests for the TASK-25 surface (multi-user v3.1).

Real ASGI app (httpx.ASGITransport + lifespan), auth_enabled=True unless
stated:
- first-run setup end-to-end (no password -> boot in setup mode -> token ->
  first operator -> setup gone);
- invitation registration (valid / unknown / used / expired code, duplicate
  username) with the timing-equalization burn on unknown codes;
- users + invitations CRUD as operator, 403 for viewer mutations, viewer
  reads allowed;
- CSRF (missing/mismatched) rejected on setup and register;
- kill-switch: auth OFF == v0.5.0 behavior (users/invitations reachable
  anonymously, setup/register 404).
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlmodel import select

from metatracer.api.app import create_app
from metatracer.api.auth import _hash_token, _utc_now
from metatracer.core.config import Settings
from metatracer.db.models import InvitationCode, User, UserRole, UserSession


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/task25-api-test.db",
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
    """Default posture: provisioned operator from METATRACER_AUTH_PASSWORD."""
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
    page = await client.get("/login")
    assert page.status_code == 200
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


async def _create_invitation(
    client: httpx.AsyncClient,
    csrf: str,
    role: str = "viewer",
    ttl_seconds: int | None = None,
) -> dict:
    body: dict = {"role": role}
    if ttl_seconds is not None:
        body["ttl_seconds"] = ttl_seconds
    response = await client.post(
        "/api/invitations", json=body, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- First-run setup ------------------------------------------------------------------


class TestSetupFlow:
    async def test_setup_end_to_end(self, tmp_path: Path):
        """No password -> boot in setup mode -> create first operator ->
        setup disabled afterwards; data routes 401 before setup."""
        app = create_app(
            _settings(tmp_path, auth_password=""), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            setup_token = app.state.setup_token
            assert isinstance(setup_token, str) and setup_token
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                # No users yet: every data route stays 401 (fail-closed boot).
                assert (await client.get("/api/runs")).status_code == 401
                assert (await client.get("/api/users")).status_code == 401

                # Wrong token -> 401.
                await client.get("/login")  # issue pre-session CSRF cookie
                csrf = client.cookies.get("csrf_token", "")
                bad = await client.post(
                    "/api/auth/setup",
                    json={"setup_token": "forged", "username": "root", "password": "first-pass-1"},
                    headers={"X-CSRF-Token": csrf},
                )
                assert bad.status_code == 401

                # Valid token -> first operator created + logged in.
                ok = await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": setup_token,
                        "username": "root",
                        "password": "first-pass-1",
                    },
                    headers={"X-CSRF-Token": csrf},
                )
                assert ok.status_code == 200, ok.text
                body = ok.json()
                assert body["username"] == "root"
                assert body["role"] == "operator"
                assert "metatracer_session" in client.cookies

                # Token consumed.
                assert app.state.setup_token is None

                # Second setup attempt: 409 (user exists).
                again = await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": setup_token,
                        "username": "root2",
                        "password": "second-pass-1",
                    },
                    headers={"X-CSRF-Token": csrf},
                )
                assert again.status_code == 409

                # The created user can now use the data API.
                me = await client.get("/api/auth/me")
                assert me.status_code == 200
                assert me.json()["username"] == "root"

    async def test_setup_404_when_provisioned_from_env(self, client: httpx.AsyncClient):
        await _login(client)
        await client.get("/login")
        csrf = client.cookies.get("csrf_token", "")
        response = await client.post(
            "/api/auth/setup",
            json={"setup_token": "whatever", "username": "root", "password": "first-pass-1"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 404

    async def test_setup_404_when_auth_disabled(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_enabled=False, auth_password=""),
            reports_dir=tmp_path / "reports",
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/auth/setup",
                    json={"setup_token": "x", "username": "root", "password": "first-pass-1"},
                )
                assert response.status_code == 404

    async def test_setup_short_password_is_422(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_password=""), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            setup_token = app.state.setup_token
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                await client.get("/login")
                csrf = client.cookies.get("csrf_token", "")
                response = await client.post(
                    "/api/auth/setup",
                    json={"setup_token": setup_token, "username": "root", "password": "short"},
                    headers={"X-CSRF-Token": csrf},
                )
                assert response.status_code == 422
                # Token NOT burned on failed setup.
                assert app.state.setup_token == setup_token

    async def test_setup_without_csrf_is_403(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_password=""), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            setup_token = app.state.setup_token
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": setup_token,
                        "username": "root",
                        "password": "first-pass-1",
                    },
                )
                assert response.status_code == 403

    async def test_setup_with_bad_csrf_is_403(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_password=""), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            setup_token = app.state.setup_token
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                await client.get("/login")
                response = await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": setup_token,
                        "username": "root",
                        "password": "first-pass-1",
                    },
                    headers={"X-CSRF-Token": "forged-token"},
                )
                assert response.status_code == 403

    async def test_setup_creates_single_session_like_login(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_password=""), reports_dir=tmp_path / "reports"
        )
        async with app.router.lifespan_context(app):
            setup_token = app.state.setup_token
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                await client.get("/login")
                csrf = client.cookies.get("csrf_token", "")
                response = await client.post(
                    "/api/auth/setup",
                    json={
                        "setup_token": setup_token,
                        "username": "root",
                        "password": "first-pass-1",
                    },
                    headers={"X-CSRF-Token": csrf},
                )
                assert response.status_code == 200
                async with app.state.session_factory() as db:
                    users = (await db.exec(select(User))).all()
                    sessions = (await db.exec(select(UserSession))).all()
                assert len(users) == 1
                assert users[0].role is UserRole.operator
                assert len(sessions) == 1  # setup behaves like login (one session)


# --- Invitation registration ----------------------------------------------------------


class TestRegisterFlow:
    async def test_register_with_valid_code(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"], role="viewer")
        assert invitation["status"] == "active"
        assert invitation["code"]

        # Redeem from a fresh client (no operator session).
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={
                    "code": invitation["code"],
                    "username": "invited",
                    "password": "invited-pass-1",
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["role"] == "viewer"
            assert body["authenticated"] is True
            me = await fresh.get("/api/auth/me")
            assert me.json()["username"] == "invited"

    async def test_register_marks_code_used(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        code = invitation["code"]
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]

        async def _redeem(username: str) -> httpx.Response:
            fresh = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
                base_url="http://testserver",
            )
            async with fresh:
                await fresh.get("/login")
                csrf = fresh.cookies.get("csrf_token", "")
                return await fresh.post(
                    "/api/auth/register",
                    json={"code": code, "username": username, "password": "invited-pass-1"},
                    headers={"X-CSRF-Token": csrf},
                )

        first = await _redeem("first-user")
        assert first.status_code == 200, first.text
        second = await _redeem("second-user")
        assert second.status_code == 401
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(InvitationCode).where(
                        InvitationCode.code_hash == _hash_token(code)
                    )
                )
            ).first()
        assert row is not None
        assert row.used_at is not None
        assert row.used_by is not None

    async def test_register_unknown_code_401(self, client: httpx.AsyncClient):
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={"code": "no-such-code", "username": "x", "password": "invited-pass-1"},
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()

    async def test_register_expired_code_401(self, client: httpx.AsyncClient, tmp_path: Path):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(InvitationCode).where(
                        InvitationCode.code_hash == _hash_token(invitation["code"])
                    )
                )
            ).first()
            assert row is not None
            row.expires_at = _utc_now() - timedelta(seconds=1)
            db.add(row)
            await db.commit()
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={
                    "code": invitation["code"],
                    "username": "expired-user",
                    "password": "invited-pass-1",
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 401

    async def test_register_duplicate_username_409(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={
                    "code": invitation["code"],
                    "username": "operator",  # already provisioned
                    "password": "invited-pass-1",
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 409

    async def test_register_short_password_422(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={"code": invitation["code"], "username": "shorty", "password": "tiny"},
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 422
            # A failed redemption must NOT burn the invitation.
            session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
            async with session_factory() as db:
                row = (
                    await db.exec(
                        select(InvitationCode).where(
                            InvitationCode.code_hash == _hash_token(invitation["code"])
                        )
                    )
                ).first()
            assert row is not None and row.used_at is None

    async def test_register_404_when_auth_disabled(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_enabled=False, auth_password=""),
            reports_dir=tmp_path / "reports",
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/auth/register",
                    json={"code": "x", "username": "y", "password": "invited-pass-1"},
                )
                assert response.status_code == 404

    async def test_register_without_csrf_is_403(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")  # cookie set, header omitted
            response = await fresh.post(
                "/api/auth/register",
                json={"code": invitation["code"], "username": "noc", "password": "invited-pass-1"},
            )
            assert response.status_code == 403

    async def test_register_with_bad_csrf_is_403(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            response = await fresh.post(
                "/api/auth/register",
                json={"code": invitation["code"], "username": "badc", "password": "invited-pass-1"},
                headers={"X-CSRF-Token": "forged"},
            )
            assert response.status_code == 403

    async def test_register_role_comes_from_code(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"], role="operator")
        fresh = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
            base_url="http://testserver",
        )
        async with fresh:
            await fresh.get("/login")
            csrf = fresh.cookies.get("csrf_token", "")
            response = await fresh.post(
                "/api/auth/register",
                json={
                    "code": invitation["code"],
                    "username": "promoted",
                    "password": "invited-pass-1",
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 200
            assert response.json()["role"] == "operator"


# --- Users admin CRUD -----------------------------------------------------------------


class TestUsersCrud:
    async def test_operator_lists_users(self, client: httpx.AsyncClient):
        await _login(client)
        response = await client.get("/api/users")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert all("password_hash" not in u for u in body["users"])

    async def test_operator_creates_user(self, client: httpx.AsyncClient):
        payload = await _login(client)
        response = await client.post(
            "/api/users",
            json={"username": "co-worker", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["username"] == "co-worker"
        assert body["role"] == "viewer"
        assert "password_hash" not in body
        assert "password" not in body

    async def test_duplicate_username_409_on_create(self, client: httpx.AsyncClient):
        payload = await _login(client)
        response = await client.post(
            "/api/users",
            json={"username": "operator", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 409

    async def test_short_password_422_on_create(self, client: httpx.AsyncClient):
        payload = await _login(client)
        response = await client.post(
            "/api/users",
            json={"username": "shorty", "password": "tiny", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 422

    async def test_invalid_role_422_on_create(self, client: httpx.AsyncClient):
        payload = await _login(client)
        response = await client.post(
            "/api/users",
            json={"username": "x", "password": "worker-pass-1", "role": "admin"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 422

    async def test_patch_role(self, client: httpx.AsyncClient):
        payload = await _login(client)
        created = await client.post(
            "/api/users",
            json={"username": "to-promote", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        user_id = created.json()["id"]
        response = await client.patch(
            f"/api/users/{user_id}",
            json={"role": "operator"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "operator"

    async def test_patch_last_operator_409(self, client: httpx.AsyncClient):
        payload = await _login(client)
        listing = await client.get("/api/users")
        operator_id = next(
            u["id"] for u in listing.json()["users"] if u["role"] == "operator"
        )
        response = await client.patch(
            f"/api/users/{operator_id}",
            json={"role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 409

    async def test_delete_user_and_last_operator_guard(
        self, client: httpx.AsyncClient
    ):
        payload = await _login(client)
        created = await client.post(
            "/api/users",
            json={"username": "temp", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        user_id = created.json()["id"]
        response = await client.delete(
            f"/api/users/{user_id}", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert response.status_code == 204
        # Unknown id afterwards: 404.
        gone = await client.delete(
            f"/api/users/{user_id}", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert gone.status_code == 404

        listing = await client.get("/api/users")
        operator_id = next(
            u["id"] for u in listing.json()["users"] if u["role"] == "operator"
        )
        last = await client.delete(
            f"/api/users/{operator_id}", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert last.status_code == 409

    async def test_self_deletion_409(self, client: httpx.AsyncClient):
        payload = await _login(client)
        me = await client.get("/api/auth/me")
        # The list response carries no id->username ambiguity: find our id.
        listing = await client.get("/api/users")
        my_id = next(
            u["id"] for u in listing.json()["users"] if u["username"] == me.json()["username"]
        )
        response = await client.delete(
            f"/api/users/{my_id}", headers={"X-CSRF-Token": payload["csrf_token"]}
        )
        assert response.status_code == 409

    async def test_viewer_cannot_read_admin_or_mutate(self, client: httpx.AsyncClient):
        payload = await _login_as_viewer(client)
        csrf = payload["csrf_token"]
        assert (await client.get("/api/users")).status_code == 403
        assert (await client.get("/api/invitations")).status_code == 403
        denied_create = await client.post(
            "/api/users",
            json={"username": "nope", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": csrf},
        )
        assert denied_create.status_code == 403
        denied_invite = await client.post(
            "/api/invitations",
            json={"role": "viewer"},
            headers={"X-CSRF-Token": csrf},
        )
        assert denied_invite.status_code == 403


# --- Invitations admin CRUD -----------------------------------------------------------


class TestInvitationsCrud:
    async def test_create_returns_code_exactly_once(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"], role="viewer")
        assert invitation["code"]
        # GET listings never carry the code.
        listing = await client.get("/api/invitations")
        assert listing.status_code == 200
        body = listing.text
        assert invitation["code"] not in body
        assert "code_hash" not in body
        assert "code" not in listing.json()["invitations"][0]
        assert listing.json()["invitations"][0]["status"] == "active"
        assert listing.json()["invitations"][0]["created_by"] == "operator"

    async def test_ttl_default_and_bounds(self, client: httpx.AsyncClient):
        payload = await _login(client)
        default_one = await _create_invitation(client, payload["csrf_token"])
        delta = default_one["status"]
        assert delta == "active"
        below = await client.post(
            "/api/invitations",
            json={"role": "viewer", "ttl_seconds": 59},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert below.status_code == 422
        above = await client.post(
            "/api/invitations",
            json={"role": "viewer", "ttl_seconds": 2_592_001},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert above.status_code == 422
        edge_ok = await client.post(
            "/api/invitations",
            json={"role": "viewer", "ttl_seconds": 60},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert edge_ok.status_code == 201

    async def test_revoke_invitation(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        response = await client.delete(
            f"/api/invitations/{invitation['id']}",
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert response.status_code == 204
        second = await client.delete(
            f"/api/invitations/{invitation['id']}",
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        assert second.status_code == 404

    async def test_expired_invitation_shows_expired(self, client: httpx.AsyncClient):
        payload = await _login(client)
        invitation = await _create_invitation(client, payload["csrf_token"])
        session_factory = client._transport.app.state.session_factory  # type: ignore[attr-defined]
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(InvitationCode).where(
                        InvitationCode.code_hash == _hash_token(invitation["code"])
                    )
                )
            ).first()
            assert row is not None
            row.expires_at = _utc_now() - timedelta(seconds=1)
            db.add(row)
            await db.commit()
        listing = await client.get("/api/invitations")
        statuses = {i["id"]: i["status"] for i in listing.json()["invitations"]}
        assert statuses[invitation["id"]] == "expired"

    async def test_created_password_never_leaks_in_listing(
        self, client: httpx.AsyncClient
    ):
        payload = await _login(client)
        await client.post(
            "/api/users",
            json={"username": "leak-check", "password": "worker-pass-1", "role": "viewer"},
            headers={"X-CSRF-Token": payload["csrf_token"]},
        )
        listing = await client.get("/api/users")
        assert "worker-pass-1" not in listing.text
        assert "password_hash" not in listing.text


# --- Kill-switch: auth disabled == v0.5.0 --------------------------------------------


class TestAuthDisabledKillSwitch:
    async def test_v050_behavior_unchanged(self, tmp_path: Path):
        app = create_app(
            _settings(tmp_path, auth_enabled=False, auth_password=""),
            reports_dir=tmp_path / "reports",
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                # Data API reachable anonymously (v0.5.0).
                assert (await client.get("/api/runs")).status_code == 200
                assert (await client.get("/api/users")).status_code == 200
                assert (await client.get("/api/invitations")).status_code == 200
                # Pre-auth setup/register are 404 (no surface when auth off).
                assert (
                    await client.post(
                        "/api/auth/setup",
                        json={"setup_token": "x", "username": "y", "password": "invited-pass-1"},
                    )
                ).status_code == 404
                assert (
                    await client.post(
                        "/api/auth/register",
                        json={"code": "x", "username": "y", "password": "invited-pass-1"},
                    )
                ).status_code == 404
                # Pages are not redirected either (v0.5.0).
                page = await client.get("/", follow_redirects=False)
                assert page.status_code == 200

    async def test_auth_disabled_pristine_install_never_dangles_invitations(
        self, tmp_path: Path
    ):
        """Auth OFF + no user at all: a code could never be redeemed (register
        is 404) and its FK would dangle — the endpoint refuses instead."""
        app = create_app(
            _settings(tmp_path, auth_enabled=False, auth_password=""),
            reports_dir=tmp_path / "reports",
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/invitations", json={"role": "viewer"}
                )
                assert response.status_code == 404
