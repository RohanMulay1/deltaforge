"""Request models + CSV import results (ARCHITECTURE.md §4.11).

Request models use ``extra="forbid"`` (no frozen — request bodies are not
shared response objects). ``CsvImportResult`` is a frozen response per §4.11.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas_portfolio import PortfolioPosition


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z.\-]+$")
    dte_max: int = Field(default=7, ge=1, le=365)
    positions: list[PortfolioPosition] | None = None


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    positions: list[PortfolioPosition] = Field(min_length=1)


class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv: str = Field(min_length=1, max_length=200_000)
    symbol: str | None = None


class CsvRowError(BaseModel):
    row_number: int
    raw: dict[str, str]
    message: str


class CsvImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    positions: list[PortfolioPosition]
    rejected: list[CsvRowError]


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str | None = None
    positions: list[PortfolioPosition] | None = None
    spot_pct_range: tuple[float, float, float]  # (lo, hi, step)
    iv_pct_range: tuple[float, float, float]
    dte_override: int | None = None


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    kind: Literal["delta_drift", "pin_risk", "gamma_spike"]
    threshold: float
    tolerance: float | None = None
    dte_window: int | None = None
    portfolio_id: str | None = None
