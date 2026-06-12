"""Initial schema: 8 tables + alert_kind enum (ARCHITECTURE.md §9.2, §9.4).

Creates the full DeltaForge persistence layer:
    portfolios, positions, saved_analyses, watchlists, watchlist_items,
    alerts, alert_events  (8 tables)

Notes:
- Every table carries a nullable indexed ``user_id`` (TenantMixin) for a future
  auth layer (§9, §12).
- ``saved_analyses.engine_mode`` is CHECK-constrained to the canonical enum
  ``{wolfram, numeric_fallback}`` (§1 rule 2 — NOT ``wolfram_cloud``).
- ``alerts.kind`` uses the Postgres ENUM ``alert_kind``, created explicitly here.

Revision ID: 0001
Revises:
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALERT_KIND_ENUM = "alert_kind"
ALERT_KINDS = ("delta_drift", "pin_risk", "gamma_spike")


def upgrade() -> None:
    bind = op.get_bind()

    # ── alert_kind ENUM (explicit lifecycle; tables reference it) ────────────
    alert_kind = postgresql.ENUM(*ALERT_KINDS, name=ALERT_KIND_ENUM)
    alert_kind.create(bind, checkfirst=True)
    # Reference without re-emitting CREATE TYPE on column DDL.
    alert_kind_ref = postgresql.ENUM(
        *ALERT_KINDS, name=ALERT_KIND_ENUM, create_type=False
    )

    # ── portfolios ───────────────────────────────────────────────────────────
    op.create_table(
        "portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "base_currency",
            sa.String(length=8),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolios")),
    )
    op.create_index(
        op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False
    )

    # ── positions ──────────────────────────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("instrument_type", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "multiplier", sa.Integer(), nullable=False, server_default="100"
        ),
        sa.Column("avg_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("strike", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("implied_vol", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column(
            "source", sa.String(length=8), nullable=False, server_default="manual"
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_positions_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.CheckConstraint(
            "instrument_type IN ('equity', 'call', 'put')",
            name=op.f("ck_positions_instrument_type_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'csv')",
            name=op.f("ck_positions_source_valid"),
        ),
        sa.CheckConstraint(
            "(instrument_type = 'equity') "
            "OR (strike IS NOT NULL AND expiry IS NOT NULL)",
            name=op.f("ck_positions_option_requires_strike_expiry"),
        ),
    )
    op.create_index(
        op.f("ix_positions_portfolio_id"),
        "positions",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_positions_symbol"), "positions", ["symbol"], unique=False
    )
    op.create_index(
        op.f("ix_positions_user_id"), "positions", ["user_id"], unique=False
    )

    # ── saved_analyses (append-only) ─────────────────────────────────────────
    op.create_table(
        "saved_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("dte_max", sa.Integer(), nullable=False),
        sa.Column("spot_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("expiry_used", sa.String(length=16), nullable=False),
        sa.Column(
            "order_flow_imbalance",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
        ),
        sa.Column(
            "pin_risk_score", sa.Numeric(precision=10, scale=6), nullable=False
        ),
        sa.Column("engine_mode", sa.String(length=20), nullable=False),
        sa.Column("wolfram_inputs", postgresql.JSONB(), nullable=True),
        sa.Column("wolfram_expressions", postgresql.JSONB(), nullable=True),
        sa.Column("wolfram_raw_result", postgresql.JSONB(), nullable=True),
        sa.Column("wolfram_computation_used", sa.Text(), nullable=True),
        sa.Column("portfolio_greeks", postgresql.JSONB(), nullable=True),
        sa.Column("hedge_recommendation", postgresql.JSONB(), nullable=True),
        sa.Column("full_response", postgresql.JSONB(), nullable=True),
        sa.Column("risk_summary", sa.Text(), nullable=True),
        sa.Column("groq_model", sa.String(length=80), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_saved_analyses_portfolio_id_portfolios"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_analyses")),
        sa.CheckConstraint(
            "engine_mode IN ('wolfram', 'numeric_fallback')",
            name=op.f("ck_saved_analyses_engine_mode_valid"),
        ),
    )
    op.create_index(
        op.f("ix_saved_analyses_portfolio_id"),
        "saved_analyses",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_analyses_symbol"),
        "saved_analyses",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_analyses_user_id"),
        "saved_analyses",
        ["user_id"],
        unique=False,
    )

    # ── watchlists ─────────────────────────────────────────────────────────────
    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "name",
            sa.String(length=120),
            nullable=False,
            server_default="Default",
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlists")),
    )
    op.create_index(
        op.f("ix_watchlists_user_id"), "watchlists", ["user_id"], unique=False
    )

    # ── watchlist_items ──────────────────────────────────────────────────────
    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.id"],
            name=op.f("fk_watchlist_items_watchlist_id_watchlists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint(
            "watchlist_id",
            "symbol",
            name=op.f("uq_watchlist_items_watchlist_id"),
        ),
    )
    op.create_index(
        op.f("ix_watchlist_items_watchlist_id"),
        "watchlist_items",
        ["watchlist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_watchlist_items_symbol"),
        "watchlist_items",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_watchlist_items_user_id"),
        "watchlist_items",
        ["user_id"],
        unique=False,
    )

    # ── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("kind", alert_kind_ref, nullable=False),
        sa.Column("threshold", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("tolerance", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("dte_window", sa.Integer(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "cooldown_seconds",
            sa.Integer(),
            nullable=False,
            server_default="3600",
        ),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_alerts_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(
        op.f("ix_alerts_portfolio_id"), "alerts", ["portfolio_id"], unique=False
    )
    op.create_index(op.f("ix_alerts_symbol"), "alerts", ["symbol"], unique=False)
    op.create_index(op.f("ix_alerts_user_id"), "alerts", ["user_id"], unique=False)

    # ── alert_events (append-only) ───────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_value", sa.Numeric(precision=18, scale=6), nullable=False
        ),
        sa.Column(
            "threshold_at_trigger",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "saved_analysis_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            name=op.f("fk_alert_events_alert_id_alerts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["saved_analysis_id"],
            ["saved_analyses.id"],
            name=op.f("fk_alert_events_saved_analysis_id_saved_analyses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
    )
    op.create_index(
        op.f("ix_alert_events_alert_id"),
        "alert_events",
        ["alert_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_events_saved_analysis_id"),
        "alert_events",
        ["saved_analysis_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_events_user_id"),
        "alert_events",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("alerts")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_table("saved_analyses")
    op.drop_table("positions")
    op.drop_table("portfolios")

    bind = op.get_bind()
    postgresql.ENUM(*ALERT_KINDS, name=ALERT_KIND_ENUM).drop(bind, checkfirst=True)
