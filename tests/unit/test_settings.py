"""Settings defaults and METATRACER_-prefixed environment overrides.

Every construction passes ``_env_file=None``: the suite must stay hermetic to
a developer's local ``.env`` (e.g. a real LLM key configured for validation).
"""

import pytest

from metatracer.core.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite+aiosqlite:///./data/metatracer.db"
    assert settings.llm_api_key.get_secret_value() == ""
    assert settings.llm_base_url == ""
    assert settings.llm_model == ""
    assert settings.fast_model == ""
    assert settings.log_level == "INFO"
    assert settings.max_assets_per_run == 50
    assert settings.max_file_bytes == 52428800
    assert settings.rate_limit_rps == 2.0
    assert settings.allow_loopback is False
    assert settings.bind_host == "127.0.0.1"
    assert settings.auth_enabled is False
    assert settings.allow_unauthenticated_bind is False


def test_env_override_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METATRACER_ALLOW_LOOPBACK", "true")
    monkeypatch.setenv("METATRACER_MAX_ASSETS_PER_RUN", "5")
    monkeypatch.setenv("METATRACER_LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.allow_loopback is True
    assert settings.max_assets_per_run == 5
    assert settings.log_level == "DEBUG"


def test_unprefixed_env_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_LOOPBACK", "true")
    assert Settings(_env_file=None).allow_loopback is False
