"""Wolfram engine configuration (pydantic-settings).

Loads the LOCAL Wolfram Engine kernel path and pool/timeout/cache knobs from the
environment. DeltaForge runs a **local Wolfram Engine 14.3 kernel** (free dev
license) via ``wolframclient``'s process-based ``WolframLanguageSession`` — NOT
Wolfram Cloud / Secured Authentication Keys.

Per ARCHITECTURE.md §5.2: a missing or unstartable kernel is NOT an error — the
service constructs fine and runs in ``numeric_fallback`` mode with
``reason="kernel_unavailable"``. No secret is ever required or hardcoded; the
kernel binary is a local install, not a credential.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the repo-root ``.env`` absolutely (see ``core/settings.py``). This
# module lives at ``<root>/backend/core/wolfram_settings.py``.
_REPO_ROOT_ENV: Path = Path(__file__).resolve().parents[2] / ".env"

# Default install location of the activated Wolfram Engine 14.3 kernel on
# Windows. Overridable via ``WOLFRAM_KERNEL_PATH``. The kernel binary is
# ``WolframKernel.exe`` (verified present in the 14.3 install dir).
DEFAULT_KERNEL_PATH = (
    r"C:\Program Files\Wolfram Research\Wolfram Engine\14.3\WolframKernel.exe"
)


class WolframSettings(BaseSettings):
    """Settings for the local Wolfram Engine symbolic kernel.

    All fields have safe defaults so the object always constructs, even with no
    environment configured. A missing/unstartable kernel → ``numeric_fallback``
    mode (``reason="kernel_unavailable"``).
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=str(_REPO_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Local kernel path (WolframKernel.exe) ────────────────────────────────
    # None → fall back to ``DEFAULT_KERNEL_PATH`` (resolved lazily so tests can
    # point at a non-existent path to exercise the fallback branch).
    wolfram_kernel_path: str | None = Field(
        default=None,
        validation_alias="WOLFRAM_KERNEL_PATH",
    )

    # ── Pool / timeout knobs ─────────────────────────────────────────────────
    # Local kernels are process-based and heavy → keep the pool small (default 2).
    wolfram_pool_size: int = Field(default=2, ge=1, le=16)
    wolfram_eval_timeout_s: float = Field(default=20.0, gt=0.0)
    wolfram_connect_timeout_s: float = Field(default=30.0, gt=0.0)
    wolfram_max_retries: int = Field(default=2, ge=0, le=10)

    # ── Cache knobs ──────────────────────────────────────────────────────────
    wolfram_cache_max: int = Field(default=2048, ge=1)

    # ── Kill-switch: forces numeric_fallback when False ──────────────────────
    wolfram_enabled: bool = True

    def resolved_kernel_path(self) -> str:
        """Return the configured kernel path, or the platform default."""
        path = (self.wolfram_kernel_path or "").strip()
        return path or DEFAULT_KERNEL_PATH

    def kernel_path_exists(self) -> bool:
        """True iff the resolved kernel binary exists on disk."""
        if not self.wolfram_enabled:
            return False
        return os.path.isfile(self.resolved_kernel_path())


@lru_cache(maxsize=1)
def get_wolfram_settings() -> WolframSettings:
    """Return a process-wide cached ``WolframSettings`` instance."""
    return WolframSettings()
