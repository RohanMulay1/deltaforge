"""HTTP routers (ARCHITECTURE.md §3). Each defines an ``APIRouter`` using the
repositories + WS0 schemas. ``main.py`` (owned by the integrator) includes them.
"""

from __future__ import annotations

from routers.history import router as history_router
from routers.portfolios import router as portfolios_router
from routers.watchlist import router as watchlist_router

__all__ = [
    "portfolios_router",
    "watchlist_router",
    "history_router",
]
