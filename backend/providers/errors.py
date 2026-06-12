"""Provider error taxonomy (ARCHITECTURE.md §7, §8.1).

These are raised by market-data providers and mapped to HTTP status codes by
the global handler in ``main.py``. They extend the domain taxonomy in
``errors.py`` where a canonical mapping already exists, and add the
provider-specific ``ProviderUnavailable`` (→503).

The ``RetryPolicy`` (``retry.py``) distinguishes *transient* provider errors
(safe to retry) from *deterministic* ones (a missing symbol is never going to
appear on a retry). Only transient errors are retried.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all market-data provider errors."""

    #: Whether a ``RetryPolicy`` should retry an operation that raised this.
    transient: bool = False


class ProviderUnavailable(ProviderError):
    """The upstream provider is unreachable / overloaded → 503.

    Transient: a transport timeout, connection reset, or 5xx from the upstream
    that is expected to recover on a subsequent attempt.
    """

    transient = True
    status_code = 503


class ProviderRateLimited(ProviderError):
    """The provider rejected the request for rate-limiting reasons → 429.

    Transient: backing off and retrying is the correct response.
    """

    transient = True
    status_code = 429


class SymbolNotFoundError(ProviderError):
    """The requested symbol does not exist upstream → 404.

    Deterministic: never retried.
    """

    transient = False
    status_code = 404


class NoChainDataError(ProviderError):
    """The symbol exists but has no usable options chain → 422.

    Deterministic: never retried.
    """

    transient = False
    status_code = 422


class UpstreamDataError(ProviderError):
    """The provider returned malformed / unusable data → 502.

    Deterministic: the payload is broken; a retry will not fix the shape.
    """

    transient = False
    status_code = 502
