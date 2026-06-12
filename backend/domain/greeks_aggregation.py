"""Pure portfolio-Greeks aggregation (ARCHITECTURE.md §8.2).

``aggregate_portfolio_greeks`` is a **pure** function:

    aggregate_greek = Σ_position  signed_qty × multiplier × per_unit_greek

Per-leg Greeks (``per_unit_greek``) are supplied by the caller — they come from
``WolframService`` (symbolic ``D[]``) for verifiability; this module never
prices anything. It consumes the canonical ``Greeks`` model from
``models`` (imported, not reimplemented) and produces a ``PortfolioGreeks``.

Equity is the degenerate case: pass ``Greeks(delta=1, gamma=0, theta=0,
vega=0, rho=0)`` and an ``OPTION``/``EQUITY`` multiplier of 1 — handled by the
caller; this function only multiplies and sums.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from models.schemas_greeks import Greeks
from models.schemas_portfolio import PortfolioGreeks

# Dollar-delta convention: net_delta_dollars = Σ delta × spot × 100 × contracts.
# Here the per-leg signed_qty × multiplier already encodes the share-equivalent
# exposure, so net_delta_dollars = aggregated_delta × spot.
_NET_DELTA_DOLLAR_NOTE = "delta × spot (delta already share-weighted)"


@dataclass(frozen=True)
class WeightedLeg:
    """A single position's signed share-equivalent weight + its per-unit Greeks.

    ``weight = signed_qty × multiplier`` (negative when short). ``per_unit`` is
    the per-CONTRACT (or per-share for equity) Greeks from Wolfram.
    """

    position_id: str
    weight: float
    per_unit: Greeks


def _zero_greeks() -> Greeks:
    return Greeks(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)


def aggregate_portfolio_greeks(
    legs: Sequence[WeightedLeg],
    spot_price: float,
    *,
    beta_weights: Mapping[str, float] | None = None,
) -> PortfolioGreeks:
    """Aggregate per-leg Greeks into a single ``PortfolioGreeks`` (pure).

    Args:
        legs: weighted legs (``weight = signed_qty × multiplier``).
        spot_price: underlying spot, used only for ``net_delta_dollars``.
        beta_weights: optional ``position_id → beta`` for a beta-weighted delta;
            when omitted ``beta_weighted_delta`` is ``None``.

    Returns:
        ``PortfolioGreeks`` with aggregate Greeks, per-position breakdown, and
        dollar/beta-weighted delta. Empty input ⇒ all-zero Greeks.
    """
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    total_rho = 0.0
    beta_delta = 0.0
    has_beta = beta_weights is not None
    per_position: dict[str, Greeks] = {}

    for leg in legs:
        w = leg.weight
        g = leg.per_unit
        leg_delta = w * g.delta
        total_delta += leg_delta
        total_gamma += w * g.gamma
        total_theta += w * g.theta
        total_vega += w * g.vega
        total_rho += w * g.rho
        if has_beta:
            beta = (beta_weights or {}).get(leg.position_id, 1.0)
            beta_delta += leg_delta * beta
        # Per-position contribution is the leg's weighted Greeks.
        per_position[leg.position_id] = Greeks(
            delta=leg_delta,
            gamma=w * g.gamma,
            theta=w * g.theta,
            vega=w * g.vega,
            rho=w * g.rho,
        )

    return PortfolioGreeks(
        delta=total_delta,
        gamma=total_gamma,
        theta=total_theta,
        vega=total_vega,
        rho=total_rho,
        net_delta_dollars=total_delta * spot_price,
        beta_weighted_delta=beta_delta if has_beta else None,
        per_position=per_position,
    )
