"""Greeks model (ARCHITECTURE.md §4.2).

``Greeks`` is the ONE canonical Greeks object on the wire. The internal
domain ``GreekSet`` dataclass maps 1:1 to this at the API boundary (§1 rule 4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Greeks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    delta: float
    gamma: float
    theta: float  # per-day decay (already /365)
    vega: float  # per 1 vol point (per 0.01 IV)
    rho: float = 0.0
