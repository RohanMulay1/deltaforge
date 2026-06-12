"""ORM model package — imports every model so ``Base.metadata`` is complete.

Alembic's ``env.py`` imports ``Base`` from this package; importing the models
here guarantees every table is registered on the shared metadata before
autogenerate / migration runs.
"""

from __future__ import annotations

from db.base import Base
from db.models.alert import (
    ALERT_KIND_ENUM_NAME,
    ALERT_KINDS,
    Alert,
    AlertEvent,
    alert_kind_enum,
)
from db.models.portfolio import Portfolio
from db.models.position import (
    EQUITY_MULTIPLIER,
    INSTRUMENT_TYPES,
    OPTION_MULTIPLIER,
    POSITION_SOURCES,
    Position,
)
from db.models.saved_analysis import ENGINE_MODES, SavedAnalysis
from db.models.watchlist import Watchlist, WatchlistItem

__all__ = [
    "Base",
    # models
    "Portfolio",
    "Position",
    "SavedAnalysis",
    "Watchlist",
    "WatchlistItem",
    "Alert",
    "AlertEvent",
    # enum object + constants
    "alert_kind_enum",
    "ALERT_KIND_ENUM_NAME",
    "ALERT_KINDS",
    "ENGINE_MODES",
    "INSTRUMENT_TYPES",
    "POSITION_SOURCES",
    "OPTION_MULTIPLIER",
    "EQUITY_MULTIPLIER",
]
