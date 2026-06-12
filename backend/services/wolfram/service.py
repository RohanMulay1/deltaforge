"""WolframService — the headline feature (ARCHITECTURE.md §5.3, §5.8).

Orchestrates the try-Wolfram-then-fallback flow. Each public method:

  1. builds the exact WL expression (``expressions.py``, pure),
  2. tries a kernel evaluation through the pool (capturing verbatim InputForm),
  3. on unavailable/timeout/kernel-message/transport failure, degrades to the
     LABELED numeric mirror (``fallback.py``),
  4. returns a frozen result DTO carrying BOTH the expression and the result.

Builders and fallback math stay pure and independently testable; only this
file knows about the kernel.

WITHOUT credentials (or without ``wolframclient`` installed) every method still
returns a valid ``numeric_fallback`` DTO — the service constructs and runs.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from core.wolfram_settings import WolframSettings, get_wolfram_settings
from services.wolfram import expressions as wl
from services.wolfram import fallback as fb
from services.wolfram.cache import EvaluationCache, LRUCacheBackend
from services.wolfram.dto import (
    FALLBACK_EVAL_TIMEOUT,
    FALLBACK_KERNEL_UNAVAILABLE,
    FALLBACK_KERNEL_UNREACHABLE,
    FALLBACK_KILL_SWITCH,
    FALLBACK_WOLFRAM_MESSAGE_ERROR,
    ComputeSource,
    GreekInputs,
    GreeksResult,
    GreeksValues,
    HedgeRequest,
    HedgeResult,
    PnLSurfaceInputs,
    PnLSurfaceResult,
    PortfolioGreeksResult,
    Position,
    WolframEvaluation,
)
from services.wolfram.session_pool import (
    EvalOutcome,
    KernelEvalError,
    KernelUnavailable,
    WolframSessionPool,
)

logger = logging.getLogger(__name__)

# Map a pool ``reason`` string onto a canonical fallback_reason (§5.6).
_REASON_TO_FALLBACK: dict[str, str] = {
    "kernel_unavailable": FALLBACK_KERNEL_UNAVAILABLE,
    "kill_switch": FALLBACK_KILL_SWITCH,
    "kernel_unreachable": FALLBACK_KERNEL_UNREACHABLE,
    "eval_timeout": FALLBACK_EVAL_TIMEOUT,
}

# Short health-cache TTL so the canary is not hammered (§5.8).
_HEALTH_TTL_S = 5.0


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class WolframService:
    """Async symbolic engine with honest Wolfram/fallback provenance."""

    def __init__(
        self,
        settings: WolframSettings | None = None,
        pool: WolframSessionPool | None = None,
        cache: EvaluationCache | None = None,
    ) -> None:
        self._settings = settings or get_wolfram_settings()
        self._pool = pool or WolframSessionPool(self._settings)
        self._cache = cache or EvaluationCache(
            LRUCacheBackend(self._settings.wolfram_cache_max)
        )
        self._started = False
        self._health_cache: tuple[float, "EngineStatusDTO"] | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the session pool. Never raises (degrades to fallback)."""
        if self._started:
            return
        await self._pool.start()
        self._started = True
        if self._pool.live_mode:
            logger.info("WolframService started in wolfram mode")
        else:
            logger.warning(
                "WolframService started in numeric_fallback mode (reason=%s)",
                self._pool.reason,
            )

    async def stop(self) -> None:
        await self._pool.stop()
        self._started = False

    @property
    def settings(self) -> WolframSettings:
        return self._settings

    # ── Internal: try kernel, capture outcome ────────────────────────────────

    async def _try_kernel(
        self, operation: str, payload_expr: str
    ) -> tuple[EvalOutcome | None, str | None]:
        """Attempt a kernel eval. Returns ``(outcome, fallback_reason)``.

        ``outcome`` is non-None on success; otherwise ``fallback_reason`` carries
        the canonical reason to label the numeric fallback with.
        """
        if not self._pool.live_mode:
            reason = self._pool.reason or "kernel_unavailable"
            return None, _REASON_TO_FALLBACK.get(reason, FALLBACK_KERNEL_UNAVAILABLE)
        try:
            outcome = await self._pool.evaluate(operation, payload_expr)
            return outcome, None
        except KernelEvalError as exc:
            logger.warning("Kernel message error for %s: %s", operation, exc)
            return None, FALLBACK_WOLFRAM_MESSAGE_ERROR
        except KernelUnavailable as exc:
            reason = getattr(exc, "reason", "kernel_unavailable")
            if reason.startswith("eval_timeout"):
                return None, FALLBACK_EVAL_TIMEOUT
            return None, _REASON_TO_FALLBACK.get(reason, FALLBACK_KERNEL_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001 - never propagate kernel faults
            logger.exception("Unexpected kernel error for %s: %s", operation, exc)
            return None, FALLBACK_KERNEL_UNAVAILABLE

    # ── Public surface ───────────────────────────────────────────────────────

    async def contract_greeks(self, c: GreekInputs) -> GreeksResult:
        """Per-contract symbolic ``D[]`` Greeks, or labeled numeric fallback."""
        operation = "contract_greeks"
        expr = wl.build_contract_greeks_expr(
            c.spot, c.strike, c.rate, c.sigma, c.t, c.cp
        )

        cached = self._cache.get(operation, expr)
        if cached is not None and cached.source is ComputeSource.WOLFRAM:
            return GreeksResult(greeks=_greeks_from_result(cached.result), evaluation=cached)

        outcome, reason = await self._try_kernel(operation, expr)
        if outcome is None:
            return fb.contract_greeks_fallback(
                c.spot, c.strike, c.rate, c.sigma, c.t, c.cp,
                fallback_reason=reason or FALLBACK_KERNEL_UNAVAILABLE,
            )

        greeks = _greeks_from_result(outcome.value)
        evaluation = WolframEvaluation(
            operation=operation,
            source=ComputeSource.WOLFRAM,
            wl_input=expr,
            wl_output=outcome.wl_output,
            result=outcome.value,
            messages=outcome.messages,
            kernel_ms=outcome.kernel_ms,
            succeeded=True,
        )
        self._cache.put(evaluation)
        return GreeksResult(greeks=greeks, evaluation=evaluation)

    async def portfolio_greeks(
        self, positions: Sequence[Position]
    ) -> PortfolioGreeksResult:
        """Aggregate ``Total[bsGreeks @@@ book]`` Greeks, or labeled fallback."""
        operation = "portfolio_greeks"
        book = _book_from_positions(positions)
        expr = wl.build_portfolio_greeks_expr(book)

        outcome, reason = await self._try_kernel(operation, expr)
        if outcome is None:
            return fb.portfolio_greeks_fallback(
                positions, fallback_reason=reason or FALLBACK_KERNEL_UNAVAILABLE
            )

        agg = _agg_from_result(outcome.value)
        # Per-position breakdown is computed numerically alongside (kernel total
        # is the verified aggregate; per-leg display is derived consistently).
        per = fb.portfolio_greeks_fallback(positions, FALLBACK_KERNEL_UNAVAILABLE)
        evaluation = WolframEvaluation(
            operation=operation,
            source=ComputeSource.WOLFRAM,
            wl_input=expr,
            wl_output=outcome.wl_output,
            result=outcome.value,
            messages=outcome.messages,
            kernel_ms=outcome.kernel_ms,
            succeeded=True,
        )
        self._cache.put(evaluation)
        return PortfolioGreeksResult(
            delta=agg["delta"],
            gamma=agg["gamma"],
            theta=agg["theta"],
            vega=agg["vega"],
            rho=agg["rho"],
            per_position=per.per_position,
            evaluation=evaluation,
        )

    async def delta_neutral_hedge(self, req: HedgeRequest) -> HedgeResult:
        """Multi-leg ``NMinimize`` hedge, or labeled numeric fallback."""
        operation = "delta_neutral_hedge"
        hedge_deltas = [leg.delta for leg in req.legs]
        per_leg_caps = [leg.max_contracts for leg in req.legs]
        expr = wl.build_hedge_nminimize_expr(
            current_delta=req.current_delta,
            hedge_deltas=hedge_deltas,
            delta_target=req.delta_target,
            lambda_penalty=req.lambda_penalty,
            per_leg_caps=per_leg_caps,
            gross_cap=req.gross_cap,
        )

        outcome, reason = await self._try_kernel(operation, expr)
        if outcome is None:
            return fb.hedge_fallback(
                req, fallback_reason=reason or FALLBACK_KERNEL_UNAVAILABLE
            )

        quantities, obj_val = _hedge_from_result(outcome.value, len(req.legs))
        residual = req.current_delta + sum(
            q * d for q, d in zip(quantities, hedge_deltas)
        ) - req.delta_target
        evaluation = WolframEvaluation(
            operation=operation,
            source=ComputeSource.WOLFRAM,
            wl_input=expr,
            wl_output=outcome.wl_output,
            result=outcome.value,
            messages=outcome.messages,
            kernel_ms=outcome.kernel_ms,
            succeeded=True,
        )
        self._cache.put(evaluation)
        return HedgeResult(
            hedge_quantities=tuple(quantities),
            residual_delta=residual,
            objective_value=obj_val,
            delta_target=req.delta_target,
            current_delta=req.current_delta,
            evaluation=evaluation,
        )

    async def pnl_surface(self, req: PnLSurfaceInputs) -> PnLSurfaceResult:
        """Symbolic P&L surface over a spot×IV grid, or labeled fallback."""
        operation = "pnl_surface"
        base_t = req.dte_override if req.dte_override is not None else fb._avg_t(req.legs)
        leg_rows = _pnl_legs_from_positions(req.legs)
        expr = wl.build_pnl_surface_expr(
            legs=leg_rows,
            base_spot=req.spot,
            base_rate=req.rate,
            spot_mults=req.spot_pcts,
            iv_shifts=req.iv_pcts,
            base_t=base_t,
        )

        outcome, reason = await self._try_kernel(operation, expr)
        if outcome is None:
            return fb.pnl_surface_fallback(
                req, fallback_reason=reason or FALLBACK_KERNEL_UNAVAILABLE
            )

        base_value, grid = _pnl_from_result(outcome.value)
        evaluation = WolframEvaluation(
            operation=operation,
            source=ComputeSource.WOLFRAM,
            wl_input=expr,
            wl_output=outcome.wl_output,
            result=outcome.value,
            messages=outcome.messages,
            kernel_ms=outcome.kernel_ms,
            succeeded=True,
        )
        self._cache.put(evaluation)
        return PnLSurfaceResult(
            pnl_grid=tuple(tuple(r) for r in grid),
            base_pnl=base_value,
            spot_pcts=tuple(req.spot_pcts),
            iv_pcts=tuple(req.iv_pcts),
            evaluation=evaluation,
        )

    async def health(self) -> "EngineStatusDTO":
        """Live canary (``1+1==2``) through the pool. Result cached ~5s (§5.8)."""
        import asyncio  # local to keep module import light

        loop = asyncio.get_event_loop()
        now = loop.time()
        if self._health_cache is not None and (now - self._health_cache[0]) < _HEALTH_TTL_S:
            return self._health_cache[1]

        status = await self._probe_health()
        self._health_cache = (now, status)
        return status

    async def _probe_health(self) -> "EngineStatusDTO":
        if not self._pool.live_mode:
            reason = self._pool.reason or "kernel_unavailable"
            return EngineStatusDTO(
                wolfram_available=False,
                engine_in_use=ComputeSource.NUMERIC_FALLBACK,
                kernel_version=None,
                pool_size=self._pool.pool_size,
                healthy_sessions=self._pool.healthy_sessions,
                last_probe_ms=None,
                reason=reason,
                note=_health_note(False, reason),
                last_checked=_now(),
            )

        outcome, reason = await self._try_kernel("health_canary", wl.build_canary_expr())
        if outcome is None or not _canary_ok(outcome.value):
            r = reason or "kernel_unavailable"
            return EngineStatusDTO(
                wolfram_available=False,
                engine_in_use=ComputeSource.NUMERIC_FALLBACK,
                kernel_version=None,
                pool_size=self._pool.pool_size,
                healthy_sessions=self._pool.healthy_sessions,
                last_probe_ms=outcome.kernel_ms if outcome else None,
                reason=r,
                note=_health_note(False, r),
                last_checked=_now(),
            )
        return EngineStatusDTO(
            wolfram_available=True,
            engine_in_use=ComputeSource.WOLFRAM,
            kernel_version=None,
            pool_size=self._pool.pool_size,
            healthy_sessions=self._pool.healthy_sessions,
            last_probe_ms=outcome.kernel_ms,
            reason=None,
            note=_health_note(True, None),
            last_checked=_now(),
        )


# ── Lightweight internal EngineStatus DTO (mapped to wire EngineStatus) ───────

from dataclasses import dataclass  # noqa: E402  (kept near its only user)


@dataclass(frozen=True)
class EngineStatusDTO:
    """Internal health snapshot; the router maps it to the wire ``EngineStatus``."""

    wolfram_available: bool
    engine_in_use: ComputeSource
    kernel_version: str | None
    pool_size: int
    healthy_sessions: int
    last_probe_ms: float | None
    reason: str | None
    note: str
    last_checked: datetime


def _health_note(available: bool, reason: str | None) -> str:
    if available:
        return "Wolfram kernel live; canary 1+1 verified == 2."
    if reason == FALLBACK_KERNEL_UNAVAILABLE or reason == "kernel_unavailable":
        return (
            "Local Wolfram Engine kernel not available; using labeled numeric "
            "fallback."
        )
    if reason == FALLBACK_KILL_SWITCH or reason == "kill_switch":
        return "Wolfram kill-switch active; using labeled numeric fallback."
    return "Wolfram kernel unavailable; using labeled numeric fallback."


# ── Result deserialization helpers ────────────────────────────────────────────


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _normalize_assoc(value: object) -> dict[str, object]:
    """Coerce a kernel Association result into a plain dict keyed by str."""
    if isinstance(value, dict):
        return {str(k).strip("'\""): v for k, v in value.items()}
    return {}


def _greeks_from_result(value: object) -> GreeksValues:
    d = _normalize_assoc(value)
    return GreeksValues(
        price=_as_float(d.get("price")),
        delta=_as_float(d.get("delta")),
        gamma=_as_float(d.get("gamma")),
        theta=_as_float(d.get("theta")),
        vega=_as_float(d.get("vega")),
        rho=_as_float(d.get("rho")),
    )


def _agg_from_result(value: object) -> dict[str, float]:
    d = _normalize_assoc(value)
    return {
        "delta": _as_float(d.get("delta")),
        "gamma": _as_float(d.get("gamma")),
        "vega": _as_float(d.get("vega")),
        "theta": _as_float(d.get("theta")),
        "rho": _as_float(d.get("rho")),
    }


def _hedge_from_result(value: object, n: int) -> tuple[list[float], float]:
    """Parse ``{objVal, {v0 -> .., v1 -> ..}}`` from NMinimize."""
    quantities = [0.0] * n
    obj_val = 0.0
    if isinstance(value, (list, tuple)) and value:
        obj_val = _as_float(value[0])
        if len(value) > 1:
            rules = value[1]
            parsed = _parse_rules(rules)
            for i in range(n):
                quantities[i] = parsed.get(f"v{i}", 0.0)
    return quantities, obj_val


def _parse_rules(rules: object) -> dict[str, float]:
    """Parse a list of ``{var -> value}`` rules into ``{name: value}``."""
    out: dict[str, float] = {}
    if isinstance(rules, dict):
        for k, v in rules.items():
            out[str(k).strip("'\"")] = _as_float(v)
    elif isinstance(rules, (list, tuple)):
        for item in rules:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out[str(item[0]).strip("'\"")] = _as_float(item[1])
    return out


def _pnl_from_result(value: object) -> tuple[float, list[list[float]]]:
    d = _normalize_assoc(value)
    base = _as_float(d.get("base"))
    raw_grid = d.get("grid")
    grid: list[list[float]] = []
    if isinstance(raw_grid, (list, tuple)):
        for row in raw_grid:
            if isinstance(row, (list, tuple)):
                grid.append([_as_float(x) for x in row])
    return base, grid


def _book_from_positions(positions: Sequence[Position]) -> list[list[float]]:
    book: list[list[float]] = []
    for pos in positions:
        qty_mult = pos.signed_qty * pos.multiplier
        if pos.is_equity:
            book.append([qty_mult, pos.spot, 0.0, pos.rate, 0.0, 0.0, 0])
        else:
            strike = pos.strike if pos.strike is not None else pos.spot
            sigma = pos.sigma if pos.sigma is not None else 0.0
            t = pos.t if pos.t is not None else 0.0
            book.append([qty_mult, pos.spot, strike, pos.rate, sigma, t, pos.cp])
    return book


def _pnl_legs_from_positions(positions: Sequence[Position]) -> list[list[float]]:
    rows: list[list[float]] = []
    for pos in positions:
        qty_mult = pos.signed_qty * pos.multiplier
        if pos.is_equity:
            rows.append([qty_mult, 0.0, 0.0, 0])
        else:
            strike = pos.strike if pos.strike is not None else pos.spot
            sigma = pos.sigma if pos.sigma is not None else 0.0
            rows.append([qty_mult, strike, sigma, pos.cp])
    return rows


def _canary_ok(value: object) -> bool:
    return abs(_as_float(value, default=-999.0) - 2.0) < 1e-9
