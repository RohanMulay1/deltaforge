"""``saved_analyses`` ORM model — APPEND-ONLY audit + Wolfram reproducibility.

ARCHITECTURE.md §9.2. The JSONB columns mirror WS0 wire shapes
(``AnalyzeResponse`` / ``HedgeRecommendation`` / ``PortfolioGreeks``) so a stored
row is replayable via ``/history/{id}``. ``engine_mode`` is CHECK-constrained to
the canonical enum ``{wolfram, numeric_fallback}`` (§1 rule 2 — NOT
``wolfram_cloud`` / ``scipy_fallback``).

This table is append-only: its repository omits update/delete (§9.3).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base, PKMixin, TenantMixin, TimestampMixin

# Canonical engine discriminator values (§1 rule 2). The CHECK constraint uses
# exactly these — a real local kernel is "wolfram", never "wolfram_cloud".
ENGINE_MODES: tuple[str, ...] = ("wolfram", "numeric_fallback")


class SavedAnalysis(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "saved_analyses"

    # SET NULL: deleting a portfolio must not erase its analysis audit trail.
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    dte_max: Mapped[int] = mapped_column(Integer, nullable=False)
    spot_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    expiry_used: Mapped[str] = mapped_column(String(16), nullable=False)
    order_flow_imbalance: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
    pin_risk_score: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    engine_mode: Mapped[str] = mapped_column(String(20), nullable=False)

    # Wolfram reproducibility payloads (mirror WolframComputation provenance).
    wolfram_inputs: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    wolfram_expressions: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    wolfram_raw_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    wolfram_computation_used: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    # Renderable payloads (mirror AnalyzeResponse sub-objects).
    portfolio_greeks: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    hedge_recommendation: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    full_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    groq_model: Mapped[str | None] = mapped_column(
        String(80), nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint(
            "engine_mode IN ('wolfram', 'numeric_fallback')",
            name="engine_mode_valid",
        ),
    )
