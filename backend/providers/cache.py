"""CachingProvider decorator (ARCHITECTURE.md §8.1).

Wraps any ``MarketDataProvider`` with per-method TTL caching and **single-flight**
de-duplication: concurrent callers for the same key await one in-flight fetch
instead of stampeding the upstream. The cache backend is an in-process TTL map
behind a small ``CacheBackend`` Protocol so P3 can swap to Redis without
touching call sites.

TTLs (§8.1): ``get_spot`` 5s, ``get_chain`` 30s, ``get_expirations`` 1h.
Keys are ``(provider.name, method, symbol, expiry)`` tuples.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

from providers.base import Quote, RawChain

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Per-method TTLs in seconds (named constants — no magic numbers at call sites).
TTL_SPOT_S = 5.0
TTL_CHAIN_S = 30.0
TTL_EXPIRATIONS_S = 3600.0

CacheKey = tuple[str, ...]


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal TTL cache surface (Redis-swappable in P3)."""

    def get(self, key: CacheKey) -> Any | None: ...

    def set(self, key: CacheKey, value: Any, ttl_s: float) -> None: ...


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    """In-process TTL cache. Lazy expiry on read; not size-bounded (P3: Redis)."""

    def __init__(self) -> None:
        self._store: dict[CacheKey, _Entry] = {}

    def get(self, key: CacheKey) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: CacheKey, value: Any, ttl_s: float) -> None:
        self._store[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_s)


class CachingProvider:
    """A ``MarketDataProvider`` decorator adding TTL cache + single-flight.

    The wrapped provider's ``name`` is preserved so it still flows into
    ``MarketSnapshot.data_source``.
    """

    def __init__(self, inner: Any, backend: CacheBackend | None = None) -> None:
        self._inner = inner
        self.name: str = inner.name
        self._cache: CacheBackend = backend or TTLCache()
        # One lock per key → single-flight (concurrent same-key callers coalesce).
        self._locks: dict[CacheKey, asyncio.Lock] = {}

    def _lock_for(self, key: CacheKey) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def _cached(
        self,
        key: CacheKey,
        ttl_s: float,
        fetch: Callable[[], Awaitable[T]],
    ) -> T:
        """Return cached value or single-flight fetch + cache."""
        hit = self._cache.get(key)
        if hit is not None:
            return hit  # type: ignore[return-value]

        async with self._lock_for(key):
            # Re-check inside the lock: a prior holder may have populated it.
            hit = self._cache.get(key)
            if hit is not None:
                return hit  # type: ignore[return-value]
            value = await fetch()
            self._cache.set(key, value, ttl_s)
            return value

    async def get_spot(self, symbol: str) -> Quote:
        sym = symbol.upper()
        key: CacheKey = (self.name, "get_spot", sym)
        return await self._cached(key, TTL_SPOT_S, lambda: self._inner.get_spot(sym))

    async def get_expirations(self, symbol: str) -> tuple[str, ...]:
        sym = symbol.upper()
        key: CacheKey = (self.name, "get_expirations", sym)
        return await self._cached(
            key, TTL_EXPIRATIONS_S, lambda: self._inner.get_expirations(sym)
        )

    async def get_chain(self, symbol: str, expiry: str) -> RawChain:
        sym = symbol.upper()
        key: CacheKey = (self.name, "get_chain", sym, expiry)
        return await self._cached(
            key, TTL_CHAIN_S, lambda: self._inner.get_chain(sym, expiry)
        )
