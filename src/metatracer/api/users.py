"""User and invitation administration (TASK-25, multi-user v3.1).

Operator-only CRUD over ``user`` accounts and single-use invitation codes.
Like every data router, the auth dependencies are wired UNCONDITIONALLY by
``app.py`` (``data_deps + action_deps``): with auth disabled they no-op and
this surface answers exactly like the v0.5.0 API (anonymous, permissive);
with auth enabled, reads need any session (operator or viewer) and mutations
need CSRF + the operator role.

Privacy invariants:
- ``password_hash``, ``token_hash`` and ``code_hash`` NEVER appear in any
  response (the response schemas below simply do not have those fields);
- an invitation's plaintext code exists exactly once — in the POST creation
  response — and is never stored, listed or logged afterward.

Integrity rules (409):
- nobody deletes their own account (an operator cannot lock themselves out);
- the LAST operator cannot be demoted or deleted (the installation must keep
  at least one operator able to administer the rest);
- invitation codes are revoked by physical DELETE (a security artifact, not
  business history), idempotently answering 404 when already gone.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from metatracer.api.auth import (
    _SESSION_TOKEN_BYTES,
    CurrentUser,
    _hash_token,
    _utc_now,
    get_current_user,
    hash_password,
)
from metatracer.core.config import Settings
from metatracer.db.models import InvitationCode, User, UserRole

router = APIRouter(prefix="/api/users", tags=["users"])
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])

_MIN_PASSWORD_CHARS = 8
# Per-invitation TTL bounds (TASK-25): 60 s minimum (nothing shorter is
# operationally meaningful) .. 30 days hard cap.
_MIN_INVITE_TTL_SECONDS = 60
_MAX_INVITE_TTL_SECONDS = 30 * 24 * 3600


# --- Response schemas (hash-free by construction) ----------------------------------


class UserResponse(BaseModel):
    """One account, without any secret material."""

    id: str
    username: str
    role: UserRole
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at,
        )


class UserListResponse(BaseModel):
    """GET /api/users: newest first."""

    total: int
    users: list[UserResponse]


def _invitation_status(invitation: InvitationCode) -> str:
    """Derived status (computed at read time, never stored)."""
    if invitation.used_at is not None or invitation.used_by is not None:
        return "used"
    if _as_utc(invitation.expires_at) <= _utc_now():
        return "expired"
    return "active"


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class InvitationResponse(BaseModel):
    """Metadata of one invitation — NEVER the plaintext code."""

    id: str
    role: UserRole
    status: str  # derived: "active" | "expired" | "used"
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_by: str | None  # resolved username of the redeemer (audit trail)
    created_by: str  # resolved username, not the raw FK

    @classmethod
    def from_invitation(
        cls,
        invitation: InvitationCode,
        creator_username: str | None,
        redeemer_username: str | None = None,
    ) -> InvitationResponse:
        return cls(
            id=invitation.id,
            role=invitation.role,
            status=_invitation_status(invitation),
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            used_at=invitation.used_at,
            used_by=(
                redeemer_username
                if redeemer_username is not None
                else ("<deleted>" if invitation.used_by is not None else None)
            ),
            created_by=creator_username or "<deleted>",
        )


class InvitationListResponse(BaseModel):
    """GET /api/invitations: newest first."""

    total: int
    invitations: list[InvitationResponse]


class InvitationCreatedResponse(InvitationResponse):
    """POST /api/invitations response: the ONLY place the plaintext code appears."""

    code: str


class UserCreate(BaseModel):
    """POST /api/users body."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: UserRole


class UserUpdate(BaseModel):
    """PATCH /api/users/{id} body: role changes only (passwords stay private)."""

    role: UserRole


class InvitationCreate(BaseModel):
    """POST /api/invitations body; ``ttl_seconds`` defaults to the instance TTL."""

    role: UserRole
    ttl_seconds: int | None = Field(
        default=None,
        ge=_MIN_INVITE_TTL_SECONDS,
        le=_MAX_INVITE_TTL_SECONDS,
    )


# --- Shared helpers ----------------------------------------------------------------


async def _count_operators_except(db, user_id: str) -> int:
    """Operators that would remain if ``user_id`` stopped being one / vanished."""
    rows = (
        await db.exec(
            select(User).where(User.role == UserRole.operator, User.id != user_id)  # type: ignore[arg-type]
        )
    ).all()
    return len(rows)


def _validate_password_length(password: str) -> None:
    """422 when the new password is shorter than the platform minimum.

    Field-level min_length stays at 1 (same shape as ``LoginRequest``); the
    real policy check happens here so the response is an explicit 422.
    """
    if len(password) < _MIN_PASSWORD_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"password must be at least {_MIN_PASSWORD_CHARS} characters",
        )


# --- User CRUD ---------------------------------------------------------------------


@router.get("", response_model=UserListResponse)
async def list_users(request: Request) -> UserListResponse:
    """List accounts (no hash material), newest first."""
    async with request.app.state.session_factory() as db:
        rows = (
            await db.exec(select(User).order_by(User.created_at.desc()))  # type: ignore[arg-type]
        ).all()
    return UserListResponse(
        total=len(rows), users=[UserResponse.from_user(u) for u in rows]
    )


@router.post("", status_code=201, response_model=UserResponse)
async def create_user(payload: UserCreate, request: Request) -> UserResponse:
    """Create an account directly (operator-only; CSRF enforced upstream)."""
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="username must not be empty")
    _validate_password_length(payload.password)
    async with request.app.state.session_factory() as db:
        if (
            await db.exec(select(User).where(User.username == username))
        ).first() is not None:
            raise HTTPException(status_code=409, detail="username already taken")
        user = User(
            username=username,
            password_hash=hash_password(payload.password),
            role=payload.role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return UserResponse.from_user(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str, payload: UserUpdate, request: Request
) -> UserResponse:
    """Change a user's role, guarding the last-operator invariant.

    Demoting the only operator would leave the installation without anyone
    able to administer users, so it is refused (409). Any other change is
    allowed — including an operator promoting a viewer.
    """
    async with request.app.state.session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if user.role == UserRole.operator and payload.role is UserRole.viewer:
            if await _count_operators_except(db, user_id) < 1:
                raise HTTPException(
                    status_code=409,
                    detail="cannot demote the last operator of this installation",
                )
        user.role = payload.role
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return UserResponse.from_user(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    request: Request,
    current: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> Response:
    """Delete an account (sessions cascade via the migration's ON DELETE).

    Self-deletion is refused (nobody locks themselves out) and the last
    operator cannot be deleted (409) — the installation must keep one admin.
    """
    async with request.app.state.session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if current is not None and user.id == current.id:
            raise HTTPException(
                status_code=409, detail="you cannot delete your own account"
            )
        if user.role == UserRole.operator and await _count_operators_except(db, user_id) < 1:
            raise HTTPException(
                status_code=409,
                detail="cannot delete the last operator of this installation",
            )
        await db.delete(user)
        await db.commit()
    return Response(status_code=204)


# --- Invitation lifecycle ----------------------------------------------------------


@invitations_router.get("", response_model=InvitationListResponse)
async def list_invitations(request: Request) -> InvitationListResponse:
    """List invitation metadata (never the codes), newest first."""
    async with request.app.state.session_factory() as db:
        rows = (
            await db.exec(
                select(InvitationCode).order_by(InvitationCode.created_at.desc())  # type: ignore[arg-type]
            )
        ).all()
        usernames = {
            user.id: user.username for user in (await db.exec(select(User))).all()
        }
    return InvitationListResponse(
        total=len(rows),
        invitations=[
            InvitationResponse.from_invitation(
                i, usernames.get(i.created_by), usernames.get(i.used_by or "")
            )
            for i in rows
        ],
    )


@invitations_router.post("", status_code=201, response_model=InvitationCreatedResponse)
async def create_invitation(
    payload: InvitationCreate,
    request: Request,
    current: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> InvitationCreatedResponse:
    """Mint one single-use invitation; the code is shown EXACTLY here, once.

    Only the SHA-256 of the code is persisted (same technique as session
    tokens), so the plaintext exists in this response and nowhere else — not
    in the database, not in logs, not in later GET responses.
    """
    settings: Settings = request.app.state.settings
    ttl_seconds = payload.ttl_seconds
    if ttl_seconds is None:
        ttl_seconds = settings.invite_ttl_seconds
    if not (_MIN_INVITE_TTL_SECONDS <= ttl_seconds <= _MAX_INVITE_TTL_SECONDS):
        raise HTTPException(
            status_code=422,
            detail=(
                f"ttl_seconds must be between {_MIN_INVITE_TTL_SECONDS} and "
                f"{_MAX_INVITE_TTL_SECONDS}"
            ),
        )
    async with request.app.state.session_factory() as db:
        if current is not None:
            creator_id, creator_username = current.id, current.username
        else:
            # Auth-disabled deployment: attribute the invitation to the first
            # operator (there is no session identity to record). With NO user
            # at all (pristine install) there is nobody who could ever redeem
            # a code (register is 404) — refuse instead of dangling a row
            # whose FK would point nowhere.
            creator = (await db.exec(select(User))).first()
            if creator is None:
                raise HTTPException(
                    status_code=404,
                    detail="invitation codes require an existing user account",
                )
            creator_id, creator_username = creator.id, creator.username
        code = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        invitation = InvitationCode(
            code_hash=_hash_token(code),
            role=payload.role,
            created_by=creator_id,
            expires_at=_utc_now() + timedelta(seconds=ttl_seconds),
        )
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)
    return InvitationCreatedResponse(
        id=invitation.id,
        role=invitation.role,
        status=_invitation_status(invitation),
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
        used_by=None,
        created_by=creator_username or "<deleted>",
        code=code,
    )


@invitations_router.delete("/{invitation_id}", status_code=204)
async def delete_invitation(invitation_id: str, request: Request) -> Response:
    """Revoke an invitation by physical delete; idempotent 404 when gone."""
    async with request.app.state.session_factory() as db:
        invitation = await db.get(InvitationCode, invitation_id)
        if invitation is None:
            raise HTTPException(status_code=404, detail="invitation not found")
        await db.delete(invitation)
        await db.commit()
    return Response(status_code=204)
