"""WolframService package — symbolic engine with honest provenance.

Public exports (ARCHITECTURE.md §5.1): ``WolframService``, ``ComputeSource``,
and the DTOs the rest of the backend consumes.
"""

from __future__ import annotations

from services.wolfram.dto import (
    ComputeSource,
    GreekInputs,
    GreeksResult,
    GreeksValues,
    HedgeLeg,
    HedgeRequest,
    HedgeResult,
    PnLSurfaceInputs,
    PnLSurfaceResult,
    PortfolioGreeksResult,
    Position,
    WolframEvaluation,
)
from services.wolfram.expressions import WL_BUILDER_VERSION
from services.wolfram.service import EngineStatusDTO, WolframService

__all__ = [
    "WolframService",
    "EngineStatusDTO",
    "ComputeSource",
    "WolframEvaluation",
    "GreekInputs",
    "GreeksResult",
    "GreeksValues",
    "HedgeLeg",
    "HedgeRequest",
    "HedgeResult",
    "PnLSurfaceInputs",
    "PnLSurfaceResult",
    "PortfolioGreeksResult",
    "Position",
    "WL_BUILDER_VERSION",
]
