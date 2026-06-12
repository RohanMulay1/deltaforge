"""Scenario surface models (ARCHITECTURE.md §4.8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .schemas_wolfram import WolframComputation


class ScenarioAxis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Literal["spot_pct", "iv_pct", "dte"]
    values: list[float]


class ScenarioSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    x_axis: ScenarioAxis  # spot_pct
    y_axis: ScenarioAxis  # iv_pct
    pnl_grid: list[list[float]]  # [y][x] portfolio P&L
    base_pnl: float
    breakeven_spot: float | None = None
    wolfram: WolframComputation  # symbolic P&L surface expr
    is_stub: bool = True  # honest: True in P0 until P2 wires it
