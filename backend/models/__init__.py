"""Canonical DeltaForge data contract (ARCHITECTURE.md §4).

Re-exports every canonical model + enum so ``from models import X`` works for
any name in the contract. The legacy ``schemas.py`` is intentionally NOT
re-exported here (the integrator handles its shim/removal in WS2).
"""

from __future__ import annotations

from .schemas_analyze import AnalyzeResponse
from .schemas_common import (
    InstrumentType,
    OptionType,
    PipelineStage,
    WolframEngine,
)
from .schemas_greeks import Greeks
from .schemas_hedge import HedgeRecommendation
from .schemas_market import IVStats, MarketSnapshot, OptionQuote
from .schemas_portfolio import Portfolio, PortfolioGreeks, PortfolioPosition
from .schemas_requests import (
    AlertCreate,
    AnalyzeRequest,
    CsvImportRequest,
    CsvImportResult,
    CsvRowError,
    PortfolioCreate,
    ScenarioRequest,
)
from .schemas_scenario import ScenarioAxis, ScenarioSurface
from .schemas_wolfram import EngineStatus, WolframComputation

__all__ = [
    # common / enums
    "OptionType",
    "WolframEngine",
    "PipelineStage",
    "InstrumentType",
    # greeks
    "Greeks",
    # wolfram
    "WolframComputation",
    "EngineStatus",
    # market
    "OptionQuote",
    "IVStats",
    "MarketSnapshot",
    # portfolio
    "PortfolioPosition",
    "PortfolioGreeks",
    "Portfolio",
    # hedge
    "HedgeRecommendation",
    # scenario
    "ScenarioAxis",
    "ScenarioSurface",
    # analyze
    "AnalyzeResponse",
    # requests
    "AnalyzeRequest",
    "PortfolioCreate",
    "CsvImportRequest",
    "CsvRowError",
    "CsvImportResult",
    "ScenarioRequest",
    "AlertCreate",
]
