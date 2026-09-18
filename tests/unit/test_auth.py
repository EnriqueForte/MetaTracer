"""Unit tests for the auth core (TASK-24): hashing, tokens, role gating.

Integration behavior (end-to-end flows over the ASGI app) lives in
tests/integration/test_api_auth.py; this module pins the primitives.
"""

import hashlib

import pytest
from fastapi import HTTPException

from metatracer.api.auth import (
    PBKDF2_ITERATIONS,
    SESSION_COOKIE_NAME,
    CurrentUser,
    _hash_token,
    _utc_now,
    hash_password,
    require_operator_action,
    verify_password,
)
from metatracer.db.models import UserRole


class TestPasswordHashing:
    def test_roundtrip_wrong_password(self):
        stored = hash_password("correct horse battery staple")
        assert verify_password("wrong password", stored) is False

    def test_roundtrip_positive(self):
        stored = hash_password("s3cret-password!")
        assert verify_password("s3cret-password!", stored) is True

    def test_format_is_versioned_and_self_describing(self):
        stored = hash_password("x")
        parts = stored.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert parts[1] == str(PBKDF2_ITERATIONS)

    def test_unique_salt_per_call(self):
        a, b = hash_password("same-password"), hash_password("same-password")
        assert a != b, "salts must be random: identical hashes leak password equality"
        assert verify_password("same-password", a)
        assert verify_password("same-password", b)

    def test_verify_rejects_malformed_stored_hash(self):
        with pytest.raises(ValueError):
            verify_password("x", "not-a-hash")
        with pytest.raises(ValueError):
            verify_password("x", "bcrypt$2b$12$abcdef")
        with pytest.raises(ValueError):
            verify_password("x", "pbkdf2_sha256$0$aaa$bbb")

    def test_iterations_match_owasp_guidance(self):
        assert PBKDF2_ITERATIONS >= 600_000


class TestSessionTokens:
    def test_token_hash_is_sha256_hex_and_deterministic(self):
        token = "abc"
        assert _hash_token(token) == hashlib.sha256(b"abc").hexdigest()
        assert _hash_token(token) == _hash_token(token)

    def test_utc_now_is_aware(self):
        assert _utc_now().tzinfo is not None

    def test_cookie_name_contract(self):
        # Client-side code (base.html flows) and tests depend on this name.
        assert SESSION_COOKIE_NAME == "metatracer_session"


class TestRoleGating:
    @pytest.mark.asyncio
    async def test_viewer_cannot_mutate_without_csrf_or_role(self):
        viewer = CurrentUser(id="u1", username="v", role=UserRole.viewer)

        class FakeRequest:
            method = "POST"
            headers = {}
            cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await require_operator_action(FakeRequest(), viewer)
        assert exc_info.value.status_code == 403
