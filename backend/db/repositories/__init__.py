"""Repository package — re-exports every repository (ARCHITECTURE.md §9.3)."""

from __future__ import annotations

from db.repositories.alert_repo import AlertEventRepository, AlertRepository
from db.repositories.analysis_repo import SavedAnalysisRepository
from db.repositories.base import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AsyncRepository,
    Repository,
)
from db.repositories.portfolio_repo import PortfolioRepository
from db.repositories.position_repo import PositionRepository
from db.repositories.watchlist_repo import WatchlistRepository

__all__ = [
    "Repository",
    "AsyncRepository",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "PortfolioRepository",
    "PositionRepository",
    "SavedAnalysisRepository",
    "WatchlistRepository",
    "AlertRepository",
    "AlertEventRepository",
]
