"""Wolfram provenance + engine status models (ARCHITECTURE.md §4.3, §4.9).

``WolframComputation`` is the canonical provenance object on the wire (§1 rule
3). The internal ``WolframEvaluation`` dataclass produced by ``WolframService``
is mapped to this at the API boundary per the §4.4 field mapping.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .schemas_common import WolframEngine


class WolframComputation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str  # "Portfolio Delta (D[price,S])"
    expression: str  # EXACT WL string sent/displayed (InputForm)
    engine: WolframEngine  # wolfram | numeric_fallback
    inputs: dict[str, float | str] = Field(default_factory=dict)  # S,K,r,sigma,T,...
    result_raw: str | None = None  # kernel ToString[..,InputForm], None on fallback
    result_numeric: float | None = None
    evaluated: bool  # True only if a real kernel ran it
    duration_ms: float | None = None
    fallback_reason: str | None = None  # set IFF engine == numeric_fallback
    error: str | None = None
    evaluated_at: datetime


class EngineStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wolfram_available: bool  # real kernel reachable (canary 1+1==2)
    engine_in_use: WolframEngine
    kernel_version: str | None = None
    pool_size: int = 0
    healthy_sessions: int = 0
    last_probe_ms: float | None = None
    reason: str | None = None  # "credentials_absent","auth_failed",...
    note: str
    last_checked: datetime
