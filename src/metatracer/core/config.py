"""Environment configuration (pydantic-settings, prefix METATRACER_).

Variable table fixed by TASK-00 subtask 0.4.1; `.env.example` documents the same
names and must never carry real secret values.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keep in sync with DEFAULT_DATABASE_URL in metatracer.db.engine.
_DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/metatracer.db"


class Settings(BaseSettings):
    """Runtime settings read from METATRACER_* environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_prefix="METATRACER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = _DEFAULT_DATABASE_URL
    # SecretStr so an accidental repr/log of Settings never prints the key.
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_model: str = ""
    fast_model: str = ""
    log_level: str = "INFO"
    max_assets_per_run: int = 50
    max_file_bytes: int = 50 * 1024 * 1024  # 52428800 bytes = 50 MiB
    rate_limit_rps: float = 2.0
    # TEST ONLY: lets the test suite reach a local mock server. Never enable elsewhere.
    allow_loopback: bool = False
    bind_host: str = "127.0.0.1"


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings. Tests construct Settings() directly instead."""
    return Settings()
