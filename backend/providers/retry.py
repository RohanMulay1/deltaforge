"""Async RetryPolicy (ARCHITECTURE.md §8.1).

Replaces the legacy synchronous ``time.sleep`` retry loop in
``market_data_agent.py`` with a non-blocking ``asyncio.sleep`` policy using
exponential backoff + **full jitter**. Only *transient* provider errors are
retried; deterministic errors (missing symbol, malformed payload) propagate
immediately.

The policy is generic over any awaitable factory: ``await policy.run(coro_fn)``
where ``coro_fn`` is a zero-arg callable returning a fresh coroutine each
attempt (a coroutine can only be awaited once, so we re-create it per try).
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from providers.errors import ProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Defaults chosen to bound worst-case latency: 3 attempts, base 0.25s, cap 4s.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.25
DEFAULT_MAX_DELAY_S = 4.0


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential-backoff-with-full-jitter retry for transient failures.

    ``max_attempts`` counts the *total* tries (1 = no retry). Backoff for
    attempt ``n`` (1-indexed) is a uniform random draw in
    ``[0, min(max_delay, base * 2**(n-1))]`` — full jitter, which avoids the
    thundering-herd retry-synchronisation problem.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay_s: float = DEFAULT_BASE_DELAY_S
    max_delay_s: float = DEFAULT_MAX_DELAY_S

    def _backoff(self, attempt: int) -> float:
        """Full-jitter backoff for a 1-indexed attempt number."""
        ceiling = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        return random.uniform(0.0, ceiling)  # noqa: S311 - jitter, not crypto

    async def run(self, factory: Callable[[], Awaitable[T]], *, op: str = "operation") -> T:
        """Run ``factory()`` with retries on transient ``ProviderError``.

        Args:
            factory: zero-arg callable returning a fresh awaitable each call.
            op: human label for log context.

        Returns:
            The awaited result of the first successful attempt.

        Raises:
            ProviderError: the last error if all transient attempts are
                exhausted, or immediately for any non-transient error.
        """
        last_error: ProviderError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await factory()
            except ProviderError as exc:
                last_error = exc
                if not exc.transient:
                    raise
                if attempt == self.max_attempts:
                    logger.warning(
                        "Retry exhausted",
                        extra={"op": op, "attempts": attempt, "error": str(exc)},
                    )
                    raise
                delay = self._backoff(attempt)
                logger.info(
                    "Transient provider error; backing off",
                    extra={"op": op, "attempt": attempt, "delay_s": round(delay, 3)},
                )
                await asyncio.sleep(delay)

        # Unreachable: the loop either returns or raises. Guard for type-checkers.
        assert last_error is not None  # noqa: S101
        raise last_error
