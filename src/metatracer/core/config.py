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
    # --- Performance & request hygiene (v2.3) -------------------------------
    # Per-client-IP HTTP rate limit at the API edge. The service is localhost-
    # bound by default, but the Docker image binds 0.0.0.0 (TASK-07), so the
    # API still needs a guard against accidental load / resource exhaustion.
    # 0 disables this guard (e.g. behind a trusted reverse proxy that already
    # rate-limits upstream).
    api_rate_limit_per_minute: int = 120
    # Cap on request bodies at the API edge. The webhooks/import endpoints
    # already stream payloads to disk when needed; this guard stops a
    # megabyte-scale body from being read into memory before validation.
    # Generous defaults: the KB/scopes imports are the only legitimate
    # consumers and both are meant to be small operational JSON files.
    max_request_body_bytes: int = 5 * 1024 * 1024  # 5242880 bytes = 5 MiB
    # --- Platform v3.0, Eje B (TASK-23) -------------------------------------
    # Max scans running at the same time in this process. 1 (default) keeps
    # the v1-v2.4 single-scan lock (ScanAlreadyRunningError); >1 relaxes it to
    # an asyncio.Semaphore (deliberate product decision — the LLM and the
    # per-domain rate limit remain the real bottleneck resources; see
    # 12-platform-v3 section 3.4).
    max_concurrent_runs: int = 1

    @property
    def api_rate_limit_enabled(self) -> bool:
        return self.api_rate_limit_per_minute > 0


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings. Tests construct Settings() directly instead."""
    return Settings()
