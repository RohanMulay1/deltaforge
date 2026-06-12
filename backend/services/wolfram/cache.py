"""Content-addressed evaluation cache (ARCHITECTURE.md §5.7).

Key = ``sha256`` of the canonical InputForm (the ``wl_input`` string) namespaced
by ``operation`` + ``WL_BUILDER_VERSION``. Store = an LRU (``cachetools``) of
size ``wolfram_cache_max``.

Rules:
  - Only SUCCESSFUL evaluations are cached — a transient outage can never pin a
    fallback result in the cache.
  - Cache hits preserve the original ``source`` and ``wl_output`` (and flip
    ``cache_hit`` to True via ``dataclasses.replace`` so the provenance stays
    honest).
  - A ``CacheBackend`` Protocol lets P3 swap to Redis without touching call
    sites.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import threading
from typing import Protocol, runtime_checkable

from cachetools import LRUCache

from services.wolfram.dto import WolframEvaluation
from services.wolfram.expressions import WL_BUILDER_VERSION

logger = logging.getLogger(__name__)


def make_cache_key(operation: str, wl_input: str) -> str:
    """Build the content-addressed cache key.

    Namespaced by operation + builder version so a builder change (which bumps
    ``WL_BUILDER_VERSION``) automatically invalidates all prior entries.
    """
    namespace = f"{operation}\x00{WL_BUILDER_VERSION}\x00".encode("utf-8")
    digest = hashlib.sha256(namespace + wl_input.encode("utf-8")).hexdigest()
    return f"{operation}:{WL_BUILDER_VERSION}:{digest}"


@runtime_checkable
class CacheBackend(Protocol):
    """Swappable cache backend (LRU now, Redis in P3)."""

    def get(self, key: str) -> WolframEvaluation | None: ...

    def set(self, key: str, value: WolframEvaluation) -> None: ...

    def clear(self) -> None: ...

    def __len__(self) -> int: ...


class LRUCacheBackend:
    """Thread-safe in-process LRU backed by ``cachetools.LRUCache``."""

    def __init__(self, max_size: int) -> None:
        self._cache: LRUCache[str, WolframEvaluation] = LRUCache(maxsize=max_size)
        self._lock = threading.Lock()

    def get(self, key: str) -> WolframEvaluation | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: WolframEvaluation) -> None:
        with self._lock:
            self._cache[key] = value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class EvaluationCache:
    """Facade over a ``CacheBackend`` enforcing the §5.7 caching policy."""

    def __init__(self, backend: CacheBackend) -> None:
        self._backend = backend

    def get(self, operation: str, wl_input: str) -> WolframEvaluation | None:
        """Return a cached evaluation with ``cache_hit=True``, or ``None``."""
        key = make_cache_key(operation, wl_input)
        hit = self._backend.get(key)
        if hit is None:
            return None
        # Preserve source + wl_output; only flip the cache_hit flag.
        return dataclasses.replace(hit, cache_hit=True)

    def put(self, evaluation: WolframEvaluation) -> None:
        """Cache an evaluation IFF it succeeded (policy §5.7)."""
        if not evaluation.succeeded:
            return
        key = make_cache_key(evaluation.operation, evaluation.wl_input)
        # Store the canonical (non-hit) form so subsequent reads label themselves.
        self._backend.set(key, dataclasses.replace(evaluation, cache_hit=False))

    def clear(self) -> None:
        self._backend.clear()

    def __len__(self) -> int:
        return len(self._backend)
