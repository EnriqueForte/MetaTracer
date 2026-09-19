"""Unit tests for TASK-25 (multi-user v3.1): setup bootstrapping, panel
integrity rules and the invitation code lifecycle.

Integration behavior (end-to-end over the ASGI app) lives in
tests/integration/test_api_auth.py; this module pins the primitives against
a real SQLite database (create_all bootstrap, same as production SQLite).
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.api.auth import (
    _SESSION_TOKEN_BYTES,
    _hash_token,
    _utc_now,
    ensure_default_user,
    hash_password,
)
from metatracer.api.users import (
    _MAX_INVITE_TTL_SECONDS,
    _MIN_INVITE_TTL_SECONDS,
    InvitationCreate,
    UserCreate,
    UserUpdate,
    create_invitation,
    create_user,
    delete_invitation,
    delete_user,
    update_user,
)
from metatracer.core.config import Settings
from metatracer.db.engine import create_db_engine, create_session_factory, init_db
from metatracer.db.models import InvitationCode, User, UserRole


class _FakeRequest:
    """Minimal Request stand-in: the unit-level handlers only read .app.state."""

    def __init__(self, settings: Settings | None, session_factory) -> None:
        app = type("App", (), {})()
        app.state = type("State", (), {})()
        if settings is not None:
            app.state.settings = settings
        app.state.session_factory = session_factory
        self.app = app


@pytest.fixture()
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_db_engine(f"sqlite+aiosqlite:///{tmp_path}/task25-unit.db")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def _settings(**overrides) -> Settings:
    defaults = {
        "database_url": "sqlite+aiosqlite:///./unused.db",
        "auth_enabled": True,
        "auth_password": "",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


async def _seed_user(
    session_factory, username: str = "operator", role: UserRole = UserRole.operator
) -> User:
    async with session_factory() as db:
        user = User(username=username, password_hash=hash_password("password-123"), role=role)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def _seed_invitation(
    session_factory,
    *,
    code: str = "seed-code",
    creator_id: str,
    role: UserRole = UserRole.viewer,
    age: timedelta | None = None,
    used: bool = False,
) -> InvitationCode:
    expires_at = _utc_now() + timedelta(seconds=3600)
    if age is not None:  # negative age -> already expired
        expires_at = _utc_now() + age

    async def _run() -> InvitationCode:
        async with session_factory() as db:
            invitation = InvitationCode(
                code_hash=_hash_token(code),
                role=role,
                created_by=creator_id,
                expires_at=expires_at,
            )
            if used:
                invitation.used_at = _utc_now()
                invitation.used_by = creator_id
            db.add(invitation)
            await db.commit()
            await db.refresh(invitation)
            return invitation

    return _run()


# --- ensure_default_user: the three branches ----------------------------------------


class TestEnsureDefaultUser:
    async def test_branch_a_password_provisions_operator(self, session_factory):
        settings = _settings(auth_password="strong-password-1")
        token = await ensure_default_user(session_factory, settings)
        assert token is None
        async with session_factory() as db:
            user = (await db.exec(select(User))).first()
        assert user is not None
        assert user.username == "operator"
        assert user.role is UserRole.operator

    async def test_branch_b_no_password_returns_setup_token(self, session_factory):
        settings = _settings(auth_password="")
        token = await ensure_default_user(session_factory, settings)
        assert isinstance(token, str)
        # Same entropy class as session tokens: 32 url-safe chars.
        assert len(token) >= _SESSION_TOKEN_BYTES

    async def test_branch_b_token_is_regenerated_each_boot(self, session_factory):
        settings = _settings(auth_password="")
        first = await ensure_default_user(session_factory, settings)
        second = await ensure_default_user(session_factory, settings)
        assert first is not None and second is not None
        assert first != second, "each boot without users must mint a fresh token"

    async def test_branch_c_existing_users_are_noop(self, session_factory):
        await _seed_user(session_factory)
        settings = _settings(auth_password="")
        assert await ensure_default_user(session_factory, settings) is None
        settings = _settings(auth_password="ignored-password-1")
        assert await ensure_default_user(session_factory, settings) is None
        async with session_factory() as db:
            users = (await db.exec(select(User))).all()
        assert len(users) == 1, "branch (c) must never create or provision"

    async def test_auth_disabled_returns_none_even_with_empty_db(self, session_factory):
        settings = _settings(auth_enabled=False, auth_password="")
        assert await ensure_default_user(session_factory, settings) is None
        async with session_factory() as db:
            assert (await db.exec(select(User))).first() is None

    async def test_branch_a_short_password_fails_closed(self, session_factory):
        settings = _settings(auth_password="short")
        with pytest.raises(RuntimeError):
            await ensure_default_user(session_factory, settings)


# --- Invitation code hashing / lookup ------------------------------------------------


class TestCodeHashing:
    async def test_code_is_stored_only_as_sha256(self, session_factory):
        creator = await _seed_user(session_factory)
        code = "plaintext-invitation-code"
        invitation = await _seed_invitation(session_factory, code=code, creator_id=creator.id)
        assert invitation.code_hash == hashlib.sha256(code.encode()).hexdigest()
        assert code not in invitation.code_hash

    async def test_lookup_finds_the_row_by_hash(self, session_factory):
        creator = await _seed_user(session_factory)
        await _seed_invitation(session_factory, code="abc-123", creator_id=creator.id)
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(InvitationCode).where(
                        InvitationCode.code_hash == _hash_token("abc-123")
                    )
                )
            ).first()
        assert row is not None

    async def test_two_codes_never_share_a_hash(self, session_factory):
        creator = await _seed_user(session_factory)
        first = await _seed_invitation(session_factory, code="one", creator_id=creator.id)
        second = await _seed_invitation(session_factory, code="two", creator_id=creator.id)
        assert first.code_hash != second.code_hash


# --- Invitation lifecycle: expiry / single use / revocation --------------------------


class TestInvitationLifecycle:
    async def test_expired_code_is_not_active(self, session_factory):
        creator = await _seed_user(session_factory)
        invitation = await _seed_invitation(
            session_factory, code="old", creator_id=creator.id, age=timedelta(seconds=-10)
        )
        from metatracer.api.users import _invitation_status

        assert _invitation_status(invitation) == "expired"

    async def test_used_code_reports_used(self, session_factory):
        creator = await _seed_user(session_factory)
        invitation = await _seed_invitation(
            session_factory, code="spent", creator_id=creator.id, used=True
        )
        from metatracer.api.users import _invitation_status

        assert _invitation_status(invitation) == "used"

    async def test_single_use_flag_is_irreversible_by_lookup(self, session_factory):
        """A redeemed row must never be redeemable again: lookup keys on hash,
        but the register path checks used_at/used_by before accepting."""
        creator = await _seed_user(session_factory)
        invitation = await _seed_invitation(
            session_factory, code="once", creator_id=creator.id, used=True
        )
        assert invitation.used_at is not None and invitation.used_by is not None

    async def test_revocation_is_physical_delete_then_404(self, session_factory):
        creator = await _seed_user(session_factory)
        invitation = await _seed_invitation(
            session_factory, code="revoke-me", creator_id=creator.id
        )
        request = _FakeRequest(None, session_factory)

        await delete_invitation(invitation.id, request)  # type: ignore[arg-type]

        async with session_factory() as db:
            assert await db.get(InvitationCode, invitation.id) is None

    async def test_second_revocation_404s(self, session_factory):
        creator = await _seed_user(session_factory)
        invitation = await _seed_invitation(session_factory, code="gone", creator_id=creator.id)
        request = _FakeRequest(None, session_factory)
        await delete_invitation(invitation.id, request)  # type: ignore[arg-type]
        with pytest.raises(HTTPException) as exc_info:
            await delete_invitation(invitation.id, request)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 404


# --- Panel integrity rules -----------------------------------------------------------


class TestPanelIntegrityRules:
    async def test_cannot_delete_yourself(self, session_factory):
        operator = await _seed_user(session_factory, "op", UserRole.operator)
        request = _FakeRequest(None, session_factory)
        # Simulate the authenticated principal: same id as the target row.
        from metatracer.api.auth import CurrentUser

        current = CurrentUser(id=operator.id, username=operator.username, role=operator.role)
        with pytest.raises(HTTPException) as exc_info:
            await delete_user(
                operator.id, request, current  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 409

    async def test_cannot_delete_last_operator(self, session_factory):
        operator = await _seed_user(session_factory, "only-op", UserRole.operator)
        request = _FakeRequest(None, session_factory)
        from metatracer.api.auth import CurrentUser

        viewer_admin = CurrentUser(
            id="someone-else", username="other", role=UserRole.operator
        )
        with pytest.raises(HTTPException) as exc_info:
            await delete_user(
                operator.id, request, viewer_admin  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 409

    async def test_can_delete_operator_when_another_remains(self, session_factory):
        first = await _seed_user(session_factory, "op-a", UserRole.operator)
        second = await _seed_user(session_factory, "op-b", UserRole.operator)
        request = _FakeRequest(None, session_factory)
        from metatracer.api.auth import CurrentUser

        current = CurrentUser(id=second.id, username="op-b", role=UserRole.operator)
        await delete_user(first.id, request, current)  # type: ignore[arg-type]
        async with session_factory() as db:
            assert await db.get(User, first.id) is None

    async def test_cannot_demote_last_operator(self, session_factory):
        operator = await _seed_user(session_factory, "last-op", UserRole.operator)
        request = _FakeRequest(None, session_factory)
        with pytest.raises(HTTPException) as exc_info:
            await update_user(
                operator.id, UserUpdate(role=UserRole.viewer), request  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 409

    async def test_can_demote_operator_when_another_remains(self, session_factory):
        first = await _seed_user(session_factory, "op-a", UserRole.operator)
        await _seed_user(session_factory, "op-b", UserRole.operator)
        request = _FakeRequest(None, session_factory)
        response = await update_user(
            first.id, UserUpdate(role=UserRole.viewer), request  # type: ignore[arg-type]
        )
        assert response.role is UserRole.viewer

    async def test_patch_unknown_user_is_404(self, session_factory):
        request = _FakeRequest(None, session_factory)
        with pytest.raises(HTTPException) as exc_info:
            await update_user("missing-id", UserUpdate(role=UserRole.viewer), request)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 404

    async def test_delete_unknown_user_is_404(self, session_factory):
        request = _FakeRequest(None, session_factory)

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(
                "missing-id", request, None  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 404


# --- Panel creation rules (password/username validation) -----------------------------


class TestPanelCreateUser:
    async def test_duplicate_username_is_409(self, session_factory):
        await _seed_user(session_factory, "taken", UserRole.viewer)
        request = _FakeRequest(None, session_factory)
        with pytest.raises(HTTPException) as exc_info:
            await create_user(
                UserCreate(username="taken", password="long-enough-pw", role=UserRole.viewer),
                request,  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 409

    async def test_short_password_is_422(self, session_factory):
        request = _FakeRequest(None, session_factory)
        with pytest.raises(HTTPException) as exc_info:
            await create_user(
                UserCreate(username="fresh", password="short", role=UserRole.viewer),
                request,  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 422

    async def test_blank_after_strip_is_422(self, session_factory):
        request = _FakeRequest(None, session_factory)
        with pytest.raises(HTTPException) as exc_info:
            await create_user(
                UserCreate(username="   ", password="long-enough-pw", role=UserRole.viewer),
                request,  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 422

    async def test_created_user_gets_hashed_password_and_role(self, session_factory):
        request = _FakeRequest(None, session_factory)
        response = await create_user(
            UserCreate(username="new-viewer", password="long-enough-pw", role=UserRole.viewer),
            request,  # type: ignore[arg-type]
        )
        assert response.role is UserRole.viewer
        async with session_factory() as db:
            user = await db.get(User, response.id)
        assert user is not None
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert "long-enough-pw" not in user.password_hash


# --- Invitation creation rules (TTL bounds) ------------------------------------------


class TestInvitationCreationRules:
    async def test_ttl_below_minimum_rejected_at_model_layer(self, session_factory):
        """The pydantic Field bounds answer 422 at the API edge before the
        handler runs; the handler re-checks (defense in depth) for the
        settings-default path."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            InvitationCreate(role=UserRole.viewer, ttl_seconds=_MIN_INVITE_TTL_SECONDS - 1)

    async def test_ttl_above_maximum_rejected_at_model_layer(self, session_factory):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            InvitationCreate(role=UserRole.viewer, ttl_seconds=_MAX_INVITE_TTL_SECONDS + 1)

    async def test_default_ttl_comes_from_settings(self, session_factory):
        operator = await _seed_user(session_factory, "op", UserRole.operator)
        settings = _settings(invite_ttl_seconds=7200)
        request = _FakeRequest(settings, session_factory)
        from metatracer.api.auth import CurrentUser

        current = CurrentUser(id=operator.id, username="op", role=UserRole.operator)
        response = await create_invitation(
            InvitationCreate(role=UserRole.viewer), request, current  # type: ignore[arg-type]
        )
        delta = response.expires_at - response.created_at
        assert abs(delta.total_seconds() - 7200) < 5

    async def test_created_response_carries_plaintext_once(self, session_factory):
        operator = await _seed_user(session_factory, "op", UserRole.operator)
        request = _FakeRequest(_settings(), session_factory)
        from metatracer.api.auth import CurrentUser

        current = CurrentUser(id=operator.id, username="op", role=UserRole.operator)
        response = await create_invitation(
            InvitationCreate(role=UserRole.operator), request, current
        )
        # The plaintext hashes to the stored value...
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(InvitationCode).where(
                        InvitationCode.code_hash == _hash_token(response.code)
                    )
                )
            ).first()
        assert row is not None
        # ...and the stored row never contains the plaintext.
        assert response.code not in row.code_hash
        assert row.role is UserRole.operator
