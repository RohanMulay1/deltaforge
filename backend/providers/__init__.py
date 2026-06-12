"""Market-data provider package (ARCHITECTURE.md §8.1).

Exports the provider Protocol + raw DTOs, the concrete ``YFinanceProvider``,
the ``CachingProvider`` decorator, the async ``RetryPolicy``, the error
taxonomy, and the ``build_market_data_provider`` factory.
"""

from __future__ import annotations

from providers.base import (
    MarketDataProvider,
    Quote,
    RawChain,
    RawContract,
)
from providers.cache import (
    TTL_CHAIN_S,
    TTL_EXPIRATIONS_S,
    TTL_SPOT_S,
    CacheBackend,
    CachingProvider,
    TTLCache,
)
from providers.errors import (
    NoChainDataError,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    SymbolNotFoundError,
    UpstreamDataError,
)
from providers.factory import build_market_data_provider
from providers.retry import RetryPolicy
from providers.yfinance_provider import YFinanceProvider

__all__ = [
    # base
    "MarketDataProvider",
    "Quote",
    "RawChain",
    "RawContract",
    # yfinance
    "YFinanceProvider",
    # caching
    "CachingProvider",
    "TTLCache",
    "CacheBackend",
    "TTL_SPOT_S",
    "TTL_CHAIN_S",
    "TTL_EXPIRATIONS_S",
    # retry
    "RetryPolicy",
    # factory
    "build_market_data_provider",
    # errors
    "ProviderError",
    "ProviderUnavailable",
    "ProviderRateLimited",
    "SymbolNotFoundError",
    "NoChainDataError",
    "UpstreamDataError",
]
