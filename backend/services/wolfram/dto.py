"""Frozen DTOs for the Wolfram service (ARCHITECTURE.md §5.5).

These are the *internal* domain objects produced by ``WolframService``. The API
boundary maps ``WolframEvaluation`` → the wire ``WolframComputation`` per §4.4;
that mapping is owned by the router layer, not here.

Everything in this module is immutable (``frozen=True``) so a computed result
can never be mutated after the trust anchor (``source``) is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ComputeSource(str, Enum):
    """The trust anchor. Identical values to the wire ``WolframEngine`` enum.

    There are exactly two values everywhere (§1 rule 2): ``wolfram`` means a real
    local Wolfram Engine kernel produced the result, ``numeric_fallback`` is the
    labeled numeric mirror. Aliases such as ``scipy_fallback`` / ``wolfram_kernel``
    / ``wolfram_cloud`` are NOT used.
    """

    WOLFRAM = "wolfram"
    NUMERIC_FALLBACK = "numeric_fallback"


# Canonical fallback-reason vocabulary (§5.6). A fallback evaluation MUST carry
# exactly one of these as a non-null ``fallback_reason``. The local-kernel build
# uses ``kernel_unavailable`` when no kernel can start (missing binary, missing
# ``wolframclient``, or a failed launch).
FALLBACK_KERNEL_UNAVAILABLE = "kernel_unavailable"
FALLBACK_KERNEL_UNREACHABLE = "kernel_unreachable"
FALLBACK_EVAL_TIMEOUT = "eval_timeout"
FALLBACK_WOLFRAM_MESSAGE_ERROR = "wolfram_message_error"
FALLBACK_KILL_SWITCH = "kill_switch"

VALID_FALLBACK_REASONS: frozenset[str] = frozenset(
    {
        FALLBACK_KERNEL_UNAVAILABLE,
        FALLBACK_KERNEL_UNREACHABLE,
        FALLBACK_EVAL_TIMEOUT,
        FALLBACK_WOLFRAM_MESSAGE_ERROR,
        FALLBACK_KILL_SWITCH,
    }
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class WolframEvaluation:
    """Immutable record of a single symbolic/numeric evaluation (§5.5).

    ``wl_output`` is the kernel's verbatim ``ToString[result, InputForm]`` — the
    customer can paste it back into Wolfram to reproduce the result. That
    round-trip *is* the anti-hallucination proof. It is ``None`` on every
    fallback path.

    Invariant (enforced in ``__post_init__``): ``source == NUMERIC_FALLBACK``
    IFF ``fallback_reason`` is set and is a valid reason; and a fallback
    evaluation never carries a non-null ``wl_output``.
    """

    operation: str
    source: ComputeSource
    wl_input: str
    wl_output: str | None
    result: Any
    messages: tuple[tuple[str, str], ...] = ()
    kernel_ms: float | None = None
    succeeded: bool = True
    cache_hit: bool = False
    fallback_reason: str | None = None
    evaluated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.source is ComputeSource.NUMERIC_FALLBACK:
            if self.fallback_reason is None:
                raise ValueError(
                    "numeric_fallback evaluation must carry a non-null fallback_reason"
                )
            if self.fallback_reason not in VALID_FALLBACK_REASONS:
                raise ValueError(
                    f"invalid fallback_reason: {self.fallback_reason!r}; "
                    f"must be one of {sorted(VALID_FALLBACK_REASONS)}"
                )
            if self.wl_output is not None:
                raise ValueError("numeric_fallback evaluation must have wl_output=None")
        else:  # WOLFRAM
            if self.fallback_reason is not None:
                raise ValueError(
                    "wolfram evaluation must not carry a fallback_reason"
                )


# ── Input DTOs ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GreekInputs:
    """Inputs for a single-contract Black-Scholes Greeks computation.

    ``sigma`` is decimal IV (0.18 = 18%). ``t`` is time to expiry in years.
    ``cp`` is +1 for a call, -1 for a put.
    """

    spot: float
    strike: float
    rate: float
    sigma: float
    t: float
    cp: int  # +1 call, -1 put

    def __post_init__(self) -> None:
        if self.cp not in (1, -1):
            raise ValueError("cp must be +1 (call) or -1 (put)")


@dataclass(frozen=True)
class HedgeLeg:
    """A candidate hedge instrument with its (already-known) per-unit delta."""

    label: str
    delta: float
    option_type: str  # "call" | "put"
    strike: float
    expiry: str
    max_contracts: float = 100.0


@dataclass(frozen=True)
class HedgeRequest:
    """Inputs for a multi-leg delta-neutral hedge optimization (§5.4)."""

    symbol: str
    current_delta: float
    delta_target: float
    legs: tuple[HedgeLeg, ...]
    spot: float
    rate: float = 0.0
    lambda_penalty: float = 1e-3
    gross_cap: float = 1000.0


@dataclass(frozen=True)
class Position:
    """Minimal position view consumed by ``portfolio_greeks``.

    ``signed_qty`` is signed (negative = short). ``multiplier`` is 100 for
    options, 1 for equity. Equity is the degenerate case (delta=1, rest=0).
    """

    symbol: str
    instrument: str  # "equity" | "call" | "put"
    signed_qty: float
    multiplier: float
    spot: float
    strike: float | None = None
    rate: float = 0.0
    sigma: float | None = None
    t: float | None = None
    position_id: str | None = None

    @property
    def is_equity(self) -> bool:
        return self.instrument == "equity"

    @property
    def cp(self) -> int:
        return -1 if self.instrument == "put" else 1


@dataclass(frozen=True)
class PnLSurfaceInputs:
    """Inputs for a symbolic P&L surface evaluation (§5.4)."""

    symbol: str
    spot: float
    rate: float
    legs: tuple[Position, ...]
    spot_pcts: tuple[float, ...]  # x-axis multipliers, e.g. (-0.1, ..., 0.1)
    iv_pcts: tuple[float, ...]  # y-axis IV shifts (additive vol points or multipliers)
    dte_override: float | None = None


# ── Result DTOs (carry BOTH the expression and the numeric result) ────────────


@dataclass(frozen=True)
class GreeksValues:
    """Plain Greeks container. Theta here is per-YEAR (UI divides by 365)."""

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass(frozen=True)
class GreeksResult:
    """Single-contract Greeks + the evaluation provenance."""

    greeks: GreeksValues
    evaluation: WolframEvaluation


@dataclass(frozen=True)
class PortfolioGreeksResult:
    """Aggregate portfolio Greeks + per-position breakdown + provenance."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    per_position: dict[str, GreeksValues]
    evaluation: WolframEvaluation


@dataclass(frozen=True)
class HedgeResult:
    """Delta-neutral hedge solution + provenance."""

    hedge_quantities: tuple[float, ...]
    residual_delta: float
    objective_value: float
    delta_target: float
    current_delta: float
    evaluation: WolframEvaluation


@dataclass(frozen=True)
class PnLSurfaceResult:
    """P&L surface grid + provenance.

    ``pnl_grid`` is indexed ``[y][x]`` (iv first, spot second) per §4.8.
    """

    pnl_grid: tuple[tuple[float, ...], ...]
    base_pnl: float
    spot_pcts: tuple[float, ...]
    iv_pcts: tuple[float, ...]
    evaluation: WolframEvaluation
