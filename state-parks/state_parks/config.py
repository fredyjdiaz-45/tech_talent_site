"""Application settings.

Everything is overridable through environment variables (prefix ``SP_``) or a
``.env`` file, so the same code runs from the CLI, the API and the scheduler.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SP_", env_file=".env", extra="ignore"
    )

    database_path: Path = PROJECT_ROOT / "data" / "state_parks.db"

    # --- HTTP behaviour -------------------------------------------------
    # These sites are small public agencies. Be a polite client: one request at
    # a time per host, a real delay between them, and a cache-friendly refresh
    # window. Tuning these up is how you get blocked.
    request_timeout: float = 30.0
    max_retries: int = 3
    retry_backoff: float = 2.0
    per_host_concurrency: int = 1
    request_delay: float = 1.0
    user_agent: str = (
        "state-parks-cabin-aggregator/0.1 (personal use; +https://github.com/)"
    )

    # --- Refresh --------------------------------------------------------
    refresh_months: int = 12
    refresh_chunk_days: int = 30
    refresh_interval_minutes: int = 360
    # Rows older than this are considered stale and re-fetched first.
    stale_after_hours: int = 24

    # Providers disabled by default can be turned on with SP_ENABLED_PROVIDERS.
    enabled_providers: list[str] = ["NC", "SC", "VA", "GA", "TN", "DE", "MD"]

    playwright_enabled: bool = False

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
