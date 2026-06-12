"""Provider factory (ARCHITECTURE.md §8.1).

``build_market_data_provider(settings, executor)`` selects a concrete provider
by the ``MARKET_DATA_PROVIDER`` env var and wraps it in ``CachingProvider``. A
provider whose credentials are missing fails fast here at startup rather than on
the first request.

Today only ``yfinance`` is wired (no creds needed). Future Tradier/Polygon
implementations register in ``_BUILDERS`` and validate their own creds.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from providers.cache import CacheBackend, CachingProvider
from providers.retry import RetryPolicy
from providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

ENV_PROVIDER = "MARKET_DATA_PROVIDER"
DEFAULT_PROVIDER = "yfinance"


def _build_yfinance(executor: ThreadPoolExecutor) -> YFinanceProvider:
    # yfinance needs no credentials.
    return YFinanceProvider(executor=executor, retry=RetryPolicy())


# Registry of provider builders keyed by the env discriminator value.
_BUILDERS: dict[str, Callable[[ThreadPoolExecutor], object]] = {
    "yfinance": _build_yfinance,
}


def build_market_data_provider(
    executor: ThreadPoolExecutor,
    *,
    provider_name: str | None = None,
    cache_backend: CacheBackend | None = None,
) -> CachingProvider:
    """Construct the configured market-data provider, wrapped in caching.

    Args:
        executor: shared ``ThreadPoolExecutor`` (owned by the app lifespan) that
            blocking provider calls run on.
        provider_name: explicit override; falls back to the ``MARKET_DATA_PROVIDER``
            env var, then to ``yfinance``.
        cache_backend: optional cache backend (P3: Redis); defaults to in-process.

    Returns:
        A ``CachingProvider`` wrapping the selected provider.

    Raises:
        ValueError: if the configured provider name is unknown (fail fast).
    """
    name = (provider_name or os.getenv(ENV_PROVIDER) or DEFAULT_PROVIDER).strip().lower()
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ValueError(
            f"unknown {ENV_PROVIDER}={name!r}; known providers: {sorted(_BUILDERS)}"
        )
    inner = builder(executor)
    logger.info("Market-data provider selected", extra={"provider": name})
    return CachingProvider(inner, backend=cache_backend)
