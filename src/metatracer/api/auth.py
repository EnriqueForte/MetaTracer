"""Authentication for the Web/API surface (TASK-24, v3.0 Eje C; TASK-25 multi-user).

TASK-24 baseline: session cookie + CSRF, stdlib-only password hashing
(supply-chain review 2026-09-18: PBKDF2-HMAC-SHA256 600k — no bcrypt/argon2/
passlib dependency; see 24-auth-basic.md for the trade-offs).

TASK-25 (multi-user v3.1) adds two pre-auth flows on the same primitives:
- First-run setup: with auth ON, no ``METATRACER_AUTH_PASSWORD`` and no users,
  the app now BOOTS (deliberate change over TASK-24) in setup mode — a
  one-shot ``secrets.token_urlsafe(32)`` token is logged to the console once
  and parked on ``app.state.setup_token`` (memory only, never the database).
  ``POST /api/auth/setup`` consumes it to create the first operator.
- Invitation registration: operators mint single-use codes (only their
  SHA-256 is stored, same technique as session tokens); redeeming a code
  creates the account with the role recorded in the code.

The CLI stays unauthenticated (localhost, documented posture);
this module only protects the Web/API surface. It never touches the pipeline,
the safety core or webhook egress: the 7 inviolable rules are unchanged.

Design: every dependency is wired UNCONDITIONALLY in the routers and no-ops
when ``settings.auth_enabled`` is False (read from ``app.state`` at request
time). That keeps the router code identical for both postures:
- auth disabled (default, v0.5.0 behavior): ``get_current_user`` returns
  ``None`` and ``require_operator_action`` allows everything.
- auth enabled: ``get_current_user`` validates the session cookie (401 on
  failure), ``require_operator_action`` additionally enforces CSRF (unsafe
  methods) and the operator role (all mutations are operator-only).

Security notes:
- Only the SHA-256 of the session token is stored; a database leak never
  yields a usable cookie. The same applies to invitation codes (TASK-25):
  only ``code_hash`` is persisted and the plaintext exists exactly once, in
  the creation response — never in logs.
- Sessions are rotated on every login (the fresh login deletes the previous
  session — anti-fixation) and expire server-side (``expires_at`` is checked
  here, not only in the cookie).
- CSRF: double-submit cookie (random, non-HttpOnly, independent of the
  session token) + ``X-CSRF-Token`` header on unsafe methods, compared with
  ``hmac.compare_digest``.
- Password login burns one PBKDF2 verification on unknown usernames so the
  response time does not reveal whether the user exists. Code redemption
  (TASK-25) burns one on an unknown code for the same reason: the response
  time must not reveal whether a code hash was found.
- SETUP TOKEN EXCEPTION (deliberate, reviewed design of TASK-25): the
  first-run setup token is the ONE secret printed to the console, once, with
  instructions. It lives only on ``app.state`` (never persisted), is
  consumed on success, and every restart without users regenerates it.
- Brute force is bounded by the existing API-edge rate limit (429 per IP).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from base64 import b64decode, b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import select

from metatracer.core.config import Settings
from metatracer.db.models import InvitationCode, User, UserRole, UserSession

logger = logging.getLogger("metatracer.api.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# --- Password hashing (stdlib only) -------------------------------------------

PBKDF2_ITERATIONS = 600_000
_PBKDF2_FORMAT = "pbkdf2_sha256"
_SALT_BYTES = 16
_HASH_BYTES = 32

# Fixed dummy input used when the username does not exist, so the PBKDF2
# computation still runs and the response time does not reveal account
# existence. Not secret — only evens out timing.
_DUMMY_SALT = b"metatracer-dummy-salt-01"
_dummy_hash_memory: list[str] = []


def _get_dummy_hash() -> str:
    """Build (once) the dummy stored-hash string used for timing equalization."""
    if not _dummy_hash_memory:
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            b"metatracer-dummy-password",
            _DUMMY_SALT,
            PBKDF2_ITERATIONS,
            dklen=_HASH_BYTES,
        )
        _dummy_hash_memory.append(
            f"{_PBKDF2_FORMAT}${PBKDF2_ITERATIONS}"
            f"${b64encode(_DUMMY_SALT).decode('ascii')}"
            f"${b64encode(derived).decode('ascii')}"
        )
    return _dummy_hash_memory[0]


def hash_password(password: str) -> str:
    """Hash a password into the self-describing versioned string.

    Format: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``. The version
    prefix lets a future rehash-on-login raise the iteration count without a
    schema migration.
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=_HASH_BYTES
    )
    return (
        f"{_PBKDF2_FORMAT}${PBKDF2_ITERATIONS}"
        f"${b64encode(salt).decode('ascii')}"
        f"${b64encode(derived).decode('ascii')}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash (constant-time compare).

    Raises ``ValueError`` on a malformed stored hash: provisioning always
    writes hashes produced by :func:`hash_password`, so a malformed value
    indicates a corrupted database, not a user mistake.
    """
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != _PBKDF2_FORMAT:
        raise ValueError(f"unsupported password hash format: {stored[:16]!r}...")
    iterations = int(parts[1])
    if iterations < 1:
        raise ValueError("invalid iteration count in stored hash")
    salt = b64decode(parts[2])
    expected = b64decode(parts[3])
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(derived, expected)


# --- Session tokens ------------------------------------------------------------

SESSION_COOKIE_NAME = "metatracer_session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
# 32 bytes of entropy -> 43 url-safe chars: not guessable, and brute force
# through the rate-limited edge is meaningless.
_SESSION_TOKEN_BYTES = 32

# SETUP_MODE message format (TASK-25): logged exactly once per boot while the
# installation has no users and no provisioned password. The setup token is
# the ONE deliberate exception to "never log secrets": it is the only channel
# to bootstrap a headless install (documented in 25-user-registration.md).
_SETUP_LOG_MESSAGE = (
    "SETUP MODE: no users yet - create the first operator at GET /setup "
    "with the setup token printed here. This is the ONLY time it is shown; "
    "restart regenerates it until setup completes."
)


def _hash_token(token: str) -> str:
    """SHA-256 hex of a session token — the only form persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    """Timezone-aware UTC now (data contract: aware timestamps everywhere)."""
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalize a stored timestamp to aware UTC for comparison.

    The data contract is timezone-aware UTC, but SQLite can hand back naive
    datetimes (it has no native tz type). A naive stored value is interpreted
    as UTC — the only sane reading given how the contract writes them.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# --- Session resolution ----------------------------------------------------------

class _InvalidSession(Exception):
    """Internal: missing, unknown or expired session cookie."""


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal, injected into handlers that need it."""

    id: str
    username: str
    role: UserRole


def _auth_settings(request: Request) -> Settings | None:
    """App settings from the lifespan; ``None`` before wiring (treated as off)."""
    return getattr(request.app.state, "settings", None)


async def _resolve_session(request: Request) -> CurrentUser:
    """Validate the session cookie against the database (raises _InvalidSession).

    Server-side validation only: the cookie carries an opaque token whose
    SHA-256 must match an unexpired ``user_session`` row. Expiry is checked
    against the stored ``expires_at``, not only the cookie's own max-age.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _InvalidSession
    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        row = (
            await db.exec(
                select(UserSession).where(UserSession.token_hash == _hash_token(token))
            )
        ).first()
        if row is None or _as_utc(row.expires_at) <= _utc_now():
            raise _InvalidSession
        user = await db.get(User, row.user_id)
        if user is None:  # corrupted state: session without user
            raise _InvalidSession
        return CurrentUser(id=user.id, username=user.username, role=user.role)


async def get_current_user(request: Request) -> CurrentUser | None:
    """FastAPI dependency for JSON API routes: resolve the session cookie.

    - auth disabled → ``None`` (anonymous allowed; v0.5.0 behavior).
    - auth enabled, no/invalid/expired session → 401.
    """
    settings = _auth_settings(request)
    if settings is None or not settings.auth_enabled:
        return None
    try:
        return await _resolve_session(request)
    except _InvalidSession:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "authentication required"
        ) from None


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_operator_action(
    request: Request,
    user: Annotated[CurrentUser | None, Depends(get_current_user)],
) -> None:
    """Dependency for mutating endpoints: CSRF + operator role.

    Wired unconditionally on every endpoint; behavior at request time:
    - auth disabled (``user is None``) → allow (v0.5.0 behavior).
    - auth enabled, SAFE method (GET/HEAD/OPTIONS): any authenticated user
      (operator or viewer) may read — this dependency only enforces the
      read-nothing rule for state-changing calls.
    - auth enabled, unsafe method: the ``user`` sub-dependency already
      returned 401 without a session; here the checks are CSRF
      (constant-time compare) and the operator role (viewers are read-only,
      403).

    The ``Depends(get_current_user)`` sub-dependency is resolved once per
    request (FastAPI caches dependency results within a request), so the
    session lookup does not run twice when both dependencies are wired.
    """
    if user is None:  # auth disabled
        return
    if request.method.upper() in _SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER_NAME, "")
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")
    if user.role is not UserRole.operator:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "operator role required for this action"
        )


# --- Login / logout -----------------------------------------------------------

class LoginRequest(BaseModel):
    """Body of POST /api/auth/login."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _secure_cookie(request: Request) -> bool:
    """``Secure`` cookie flag: only when TLS is actually in play.

    Plain-HTTP deployments (localhost dev, Docker on the LAN) must keep
    working, and ``Secure`` would make the browser drop the cookie there —
    it adds nothing on a hop that is plain HTTP end to end. The flag is set
    when TLS terminates at a reverse proxy (``X-Forwarded-Proto: https``) or
    the request itself is https and not local.
    """
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "::1", "testclient")
    if request.headers.get("x-forwarded-proto", "").lower() == "https":
        return True
    return request.url.scheme == "https" and not is_local


def _cookie_params(request: Request, http_only: bool) -> dict:
    return {
        "httponly": http_only,
        "samesite": "lax",
        "secure": _secure_cookie(request),
        "path": "/",
    }


def _ensure_csrf_cookie(request: Request, response: Response, settings: Settings) -> None:
    """Set a random CSRF cookie if the request does not already carry one.

    Pre-session CSRF (review 2026-09-18): the login POST itself is a mutation
    and must pass the double-submit check, so every page render issues a
    throwaway CSRF token first. The value is random and unrelated to the
    session; login rotates it together with the session.
    """
    if request.cookies.get(CSRF_COOKIE_NAME):
        return
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(_SESSION_TOKEN_BYTES),
        max_age=settings.session_ttl_seconds,
        **_cookie_params(request, http_only=False),
    )


async def _create_session_and_cookies(
    db, user_id: str, settings: Settings
) -> tuple[str, str]:
    """Create one fresh session row for ``user_id``; return ``(token, csrf)``.

    Shared by login, setup and register (TASK-25): the caller is inside an
    open session and commits; the cookie values are only generated here and
    returned so the endpoint can set them after the transaction closes.
    """
    token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
    csrf = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
    expires_at = _utc_now() + timedelta(seconds=settings.session_ttl_seconds)
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return token, csrf


def _set_session_cookies(
    request: Request, response: Response, token: str, csrf: str, settings: Settings
) -> None:
    """Set the session + CSRF cookies for a freshly created session.

    The CSRF cookie rotates with the session (any pre-session value issued by
    the page render is replaced). Readable by JS by design (double-submit
    pattern); random, independent of the session token.
    """
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_seconds,
        **_cookie_params(request, http_only=True),
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf,
        max_age=settings.session_ttl_seconds,
        **_cookie_params(request, http_only=False),
    )


def _pre_session_csrf(request: Request, response: Response, settings: Settings) -> None:
    """Enforce the pre-session double-submit for public auth POSTs.

    Shared by login, setup and register (TASK-25): the endpoint is reachable
    without a session, so the mutation is protected by a throwaway CSRF cookie
    that the page render issued first. No-op when auth is OFF (kill-switch
    symmetry: no public flow succeeds then anyway).
    """
    if not settings.auth_enabled:
        return
    _ensure_csrf_cookie(request, response, settings)
    header = request.headers.get(CSRF_HEADER_NAME, "")
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")


@router.post("/login")
async def login_endpoint(
    body: LoginRequest, request: Request, response: Response
) -> dict:
    """Verify credentials, create a fresh session, set cookies.

    Rotation: every successful login creates a NEW session row and deletes
    the user's previous sessions (one active session per user keeps the
    surface tiny; a re-login also invalidates a stale stolen cookie).
    Unknown usernames burn one PBKDF2 verification to even out timing.

    Login-CSRF (review 2026-09-18): a cross-site POST could log the victim
    into the attacker's account (or rotate away a legitimate session with
    SameSite=Lax). Mitigation: the double-submit check applies here too —
    the CSRF cookie is issued by any page render (middleware-protected pages
    and /login itself always fetch a fresh one via _ensure_csrf_cookie), so
    an attacker without that random value cannot mount login-CSRF.
    """
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory
    # Pre-session CSRF only matters when auth is ON (kill-switch symmetry:
    # with auth OFF no login succeeds anyway, and keeping the check OFF here
    # matches logout/me behavior for the auth-disabled deployment).
    if settings.auth_enabled:
        _ensure_csrf_cookie(request, response, settings)
        header = request.headers.get(CSRF_HEADER_NAME, "")
        cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
        if not header or not cookie or not hmac.compare_digest(header, cookie):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")
    async with session_factory() as db:
        stored = (
            await db.exec(select(User).where(User.username == body.username))
        ).first()
        if stored is None:
            verify_password(body.password, _get_dummy_hash())
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid credentials"
            )
        if not verify_password(body.password, stored.password_hash):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid credentials"
            )

        incoming = request.cookies.get(SESSION_COOKIE_NAME)
        if incoming:
            stale = (
                await db.exec(
                    select(UserSession).where(
                        UserSession.token_hash == _hash_token(incoming)
                    )
                )
            ).first()
            if stale is not None:
                await db.delete(stale)
        for other in (
            await db.exec(select(UserSession).where(UserSession.user_id == stored.id))
        ).all():
            await db.delete(other)

        token, csrf = await _create_session_and_cookies(db, stored.id, settings)
    _set_session_cookies(request, response, token, csrf, settings)
    logger.info("user logged in", extra={"user": stored.username})
    return {
        "authenticated": True,
        "username": stored.username,
        "role": stored.role.value,
        "csrf_token": csrf,
    }


@router.post("/logout")
async def logout_endpoint(request: Request, response: Response) -> dict:
    """Delete the session row (if any) and expire both cookies.

    CSRF applies here too (review 2026-09-18): a cross-site POST could force
    a logout (session DoS). The caller holds a valid session anyway, so the
    same double-submit check costs nothing.
    """
    settings = _auth_settings(request)
    if settings is not None and settings.auth_enabled:
        header = request.headers.get(CSRF_HEADER_NAME, "")
        cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
        if not header or not cookie or not hmac.compare_digest(header, cookie):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")
    session_factory = getattr(request.app.state, "session_factory", None)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if settings is not None and settings.auth_enabled and token and session_factory:
        async with session_factory() as db:
            row = (
                await db.exec(
                    select(UserSession).where(
                        UserSession.token_hash == _hash_token(token)
                    )
                )
            ).first()
            if row is not None:
                await db.delete(row)
                await db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me_endpoint(request: Request) -> dict:
    """Diagnostic: who is the caller (never exposes hashes or tokens)."""
    settings = _auth_settings(request)
    if settings is None or not settings.auth_enabled:
        return {"authenticated": False}
    try:
        user = await _resolve_session(request)
    except _InvalidSession:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "authentication required"
        ) from None
    return {
        "authenticated": True,
        "username": user.username,
        "role": user.role.value,
    }


# --- Provisioning / first-run setup (TASK-25) --------------------------------------

_MIN_PASSWORD_CHARS = 8


class SetupRequest(BaseModel):
    """Body of POST /api/auth/setup (first operator creation)."""

    setup_token: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    """Body of POST /api/auth/register (invitation redemption)."""

    code: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _validate_password_length(password: str) -> None:
    """422 when the new password is shorter than the platform minimum.

    Field-level min_length stays at 1 (same shape as ``LoginRequest``); the
    real policy check happens here so the response is an explicit 422.
    """
    if len(password) < _MIN_PASSWORD_CHARS:
        raise HTTPException(
            422, f"password must be at least {_MIN_PASSWORD_CHARS} characters"
        )


async def ensure_default_user(session_factory, settings: Settings) -> str | None:
    """Bootstrap the first user on boot (auth enabled only); three branches.

    - (a) ``METATRACER_AUTH_PASSWORD`` set: provision the initial operator
      exactly like TASK-24 (compatibility). Setup mode stays disabled.
    - (b) auth ON, no password, no users: SETUP MODE — generate a one-shot
      setup token (``secrets.token_urlsafe(32)``), log it to the console
      ONCE with instructions (deliberate, documented exception to "never log
      secrets": it is the only bootstrap channel for a headless install) and
      return it so the lifespan parks it on ``app.state.setup_token``. The
      app boots normally; every route still requires a session, so nothing
      is exposed — without setup there is no usable surface (fail-closed).
    - (c) users already exist: no-op (``None``).

    Returns the setup token when branch (b) applies, else ``None``. The token
    lives only in memory; every restart without users regenerates it.
    """
    if not settings.auth_enabled:
        return None
    async with session_factory() as db:
        existing = (await db.exec(select(User))).first()
        if existing is not None:
            return None  # branch (c): already provisioned
        password = settings.auth_password.get_secret_value()
        if password:
            # Branch (a): TASK-24 provisioning, unchanged.
            if len(password) < _MIN_PASSWORD_CHARS:
                raise RuntimeError(
                    "METATRACER_AUTH_PASSWORD must be at least 8 characters "
                    "(fail-closed: a network-exposed platform needs a real password)"
                )
            db.add(
                User(
                    username="operator",
                    password_hash=hash_password(password),
                    role=UserRole.operator,
                )
            )
            await db.commit()
            logger.info("initial operator provisioned from METATRACER_AUTH_PASSWORD")
            return None
        # Branch (b): setup mode. The token is memory-only (app.state) and is
        # consumed by POST /api/auth/setup on success.
        setup_token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        logger.warning("")
        logger.warning(_SETUP_LOG_MESSAGE)
        logger.warning("setup token: %s", setup_token)
        logger.warning("")
        return setup_token


@router.post("/setup")
async def setup_endpoint(
    body: SetupRequest, request: Request, response: Response
) -> dict:
    """Create the first operator with the one-shot console setup token.

    Reachable only when ALL of these hold: auth ON, no user provisioned from
    the environment, no user in the table and a live setup token on
    ``app.state``. Any other posture answers 404 (setup disabled) or 409
    (already has users) so the endpoint never becomes a standing account
    factory. On success it behaves like a login: fresh session + CSRF
    cookies, and the token is burned from memory.
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "authentication is disabled on this installation"
        )
    session_factory = request.app.state.session_factory
    # Posture check BEFORE the token compare: the 409/404 split must not
    # depend on token possession (any caller can learn this much, and the
    # token itself is never echoed back).
    async with session_factory() as db:
        existing = (await db.exec(select(User))).first()
    if existing is not None:
        if getattr(request.app.state, "setup_completed", False):
            # This very installation just completed setup in this process.
            raise HTTPException(
                status.HTTP_409_CONFLICT, "this installation already has a user"
            )
        # Provisioned from METATRACER_AUTH_PASSWORD (or pre-TASK-25 database):
        # the setup flow is permanently disabled here (404, per contract).
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "setup is not available for this installation"
        )
    if request.app.state.setup_token is None:
        # No users, no live token: setup mode was never entered on this boot.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "setup is not available")
    if not hmac.compare_digest(str(request.app.state.setup_token), body.setup_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid setup token")
    _pre_session_csrf(request, response, settings)
    _validate_password_length(body.password)
    username = body.username.strip()
    async with session_factory() as db:
        user = User(
            username=username,
            password_hash=hash_password(body.password),
            role=UserRole.operator,
        )
        db.add(user)
        await db.flush()
        token, csrf = await _create_session_and_cookies(db, user.id, settings)
    # Burn the token ONLY after the user was committed (a failed setup leaves
    # the token valid for a corrected retry). The completed flag distinguishes
    # "setup done here" (409 on retries) from "provisioned from env" (404).
    request.app.state.setup_token = None
    request.app.state.setup_completed = True
    _set_session_cookies(request, response, token, csrf, settings)
    logger.info("first operator created via setup", extra={"user": username})
    return {
        "authenticated": True,
        "username": username,
        "role": UserRole.operator.value,
        "csrf_token": csrf,
    }


@router.post("/register")
async def register_endpoint(
    body: RegisterRequest, request: Request, response: Response
) -> dict:
    """Redeem an invitation code: create the user, mark the code used, log in.

    The code is looked up by its SHA-256 (only hashes are persisted). Unknown,
    used and expired codes all answer the SAME generic 401, and an unknown
    code burns one PBKDF2 verification so the response time does not reveal
    whether a code hash exists (same technique as the login dummy hash).
    The redeemed user gets the role recorded in the code by its creator.
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "authentication is disabled on this installation"
        )
    _pre_session_csrf(request, response, settings)
    _validate_password_length(body.password)
    username = body.username.strip()
    code_hash = _hash_token(body.code)
    session_factory = request.app.state.session_factory
    async with session_factory() as db:
        # The plaintext role travels in the code: one read for it (and to
        # distinguish an unknown code, which burns one PBKDF2 verification so
        # the response time does not reveal whether the hash exists — same
        # technique as the login dummy hash).
        invitation = (
            await db.exec(
                select(InvitationCode).where(InvitationCode.code_hash == code_hash)
            )
        ).first()
        if invitation is None:
            verify_password(body.password, _get_dummy_hash())
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid invitation code")
        if (
            await db.exec(select(User).where(User.username == username))
        ).first() is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "username already taken"
            )
        user = User(
            username=username,
            password_hash=hash_password(body.password),
            role=invitation.role,
        )
        db.add(user)
        await db.flush()
        # Race-safe single-use claim (security review 2026-09-19, MEDIUM):
        # the naive read-then-mark sequence let two concurrent registers
        # redeem the same code. The claim is ONE conditional UPDATE (atomic
        # in both backends: Postgres row-locks the row, SQLite is a single
        # writer); rowcount 0 means already claimed, expired or deleted —
        # the raised 401 rolls this transaction back, so the loser of the
        # race also rolls back its just-created user row.
        claimed = 0
        result = await db.exec(
            update(InvitationCode)
            .where(
                InvitationCode.code_hash == code_hash,
                InvitationCode.used_at.is_(None),
                InvitationCode.used_by.is_(None),
                InvitationCode.expires_at > _utc_now(),
            )
            .values(used_at=_utc_now(), used_by=user.id)
            # The claim is enforced by the DATABASE, not by Python-side row
            # synchronization: "evaluate" would re-run the WHERE against
            # in-session objects and compare SQLite's naive datetimes with
            # the aware bound param (TypeError). Nothing needs syncing — the
            # transaction commits right after.
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount
        if claimed == 0:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid invitation code")
        token, csrf = await _create_session_and_cookies(db, user.id, settings)
    _set_session_cookies(request, response, token, csrf, settings)
    logger.info(
        "user registered from invitation code", extra={"user": username}
    )
    return {
        "authenticated": True,
        "username": username,
        "role": user.role.value,
        "csrf_token": csrf,
    }


# --- Provisioning (TASK-24 compatibility path) --------------------------------------
