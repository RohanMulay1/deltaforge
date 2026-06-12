"""Application settings (pydantic-settings) — ARCHITECTURE.md §11.3.

Required secrets have NO defaults so the process fails fast at boot if they are
absent: ``GROQ_API_KEY`` and ``DATABASE_URL``. The Wolfram engine needs no
secret (the kernel binary is a local install, configured via the optional
``WOLFRAM_KERNEL_PATH`` handled in ``core/wolfram_settings.py``).

Never hardcode secrets. ``.env`` is git-ignored; ``.env.example`` documents
placeholders.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the repo-root ``.env`` absolutely so the loader works regardless of
# the process CWD (the app boots from ``backend/`` but secrets live at the
# repository root). ``settings.py`` is ``<root>/backend/core/settings.py``.
_REPO_ROOT_ENV: Path = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Process-wide application settings.

    ``GROQ_API_KEY`` and ``DATABASE_URL`` are required (no defaults) — a missing
    value raises ``ValidationError`` at construction, failing the boot fast.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=str(_REPO_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Required secrets (fail-fast: no defaults) ────────────────────────────
    groq_api_key: str = Field(validation_alias="GROQ_API_KEY", min_length=1)
    database_url: str = Field(validation_alias="DATABASE_URL", min_length=1)

    # ── Optional knobs ───────────────────────────────────────────────────────
    # Optional local Wolfram kernel override (the kernel needs no secret).
    wolfram_kernel_path: str | None = Field(
        default=None,
        validation_alias="WOLFRAM_KERNEL_PATH",
    )

    # Comma-separated CORS allowlist (NEVER "*"). Parsed by ``core/cors.py``.
    cors_allow_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ALLOW_ORIGINS",
    )

    # Market-data provider selector (consumed by WS1's provider factory).
    market_data_provider: str = Field(
        default="yfinance",
        validation_alias="MARKET_DATA_PROVIDER",
    )

    # ── Rate-limit knobs (slowapi; see core/ratelimit.py) ────────────────────
    rate_limit_default: str = Field(
        default="120/minute",
        validation_alias="RATE_LIMIT_DEFAULT",
    )
    rate_limit_analyze: str = Field(
        default="30/minute",
        validation_alias="RATE_LIMIT_ANALYZE",
    )
    rate_limit_stream: str = Field(
        default="60/minute",
        validation_alias="RATE_LIMIT_STREAM",
    )
    rate_limit_enabled: bool = Field(
        default=True,
        validation_alias="RATE_LIMIT_ENABLED",
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """Reject obviously malformed DSNs early (fail-fast at boot)."""
        if "://" not in value:
            raise ValueError("DATABASE_URL must be a valid DSN (scheme://...)")
        return value

    def cors_origins_list(self) -> list[str]:
        """Return the CORS allowlist as a clean list (never ``["*"]``)."""
        origins = [o.strip() for o in self.cors_allow_origins.split(",")]
        return [o for o in origins if o and o != "*"]

    def async_database_url(self) -> str:
        """Return the DSN normalized to the asyncpg driver for the app runtime."""
        return _normalize_async_dsn(self.database_url)

    def sync_database_url(self) -> str:
        """Return the DSN normalized to the sync psycopg driver for Alembic."""
        return _normalize_sync_dsn(self.database_url)


def _normalize_async_dsn(dsn: str) -> str:
    """Coerce a Postgres DSN to ``postgresql+asyncpg://`` for the app runtime."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql+psycopg://"):
        return dsn.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+asyncpg://", 1)
    return dsn


def _normalize_sync_dsn(dsn: str) -> str:
    """Coerce a Postgres DSN to ``postgresql+psycopg://`` for the Alembic runner."""
    if dsn.startswith("postgresql+psycopg://"):
        return dsn
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+psycopg://", 1)
    return dsn


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance (fail-fast on boot)."""
    return Settings()  # type: ignore[call-arg]
