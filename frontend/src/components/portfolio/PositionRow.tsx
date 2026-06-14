"use client";

/**
 * PositionRow — one leg in the rail's positions list (ARCHITECTURE.md §10.3).
 * Shows instrument badge, signed quantity (long/short colored), strike/expiry
 * for options, and the per-leg delta wrapped in `<Explainable>` when the leg
 * carries kernel provenance. A remove button deletes the leg from client state.
 */

import { Explainable } from "@/components/explain/Explainable";
import type { RailPosition } from "@/hooks/usePortfolio";

interface PositionRowProps {
  position: RailPosition;
  onRemove: (id: string) => void;
}

const UP = "var(--df-up, #05b169)";
const DOWN = "var(--df-down, #cf202f)";
const DIM = "var(--df-text-dim, #a8acb3)";
const MUTED = "var(--df-text-muted, #7c828a)";

function instrumentStyle(instrument: string): React.CSSProperties {
  if (instrument === "call") {
    return { background: "rgba(245,166,35,0.12)", color: "var(--df-accent, #f5a623)", border: "1px solid rgba(245,166,35,0.25)" };
  }
  if (instrument === "put") {
    return { background: "rgba(207,32,47,0.10)", color: DOWN, border: "1px solid rgba(207,32,47,0.25)" };
  }
  return { background: "var(--df-border)", color: DIM, border: "1px solid var(--df-border-strong)" };
}

export function PositionRow({ position, onRemove }: PositionRowProps) {
  const isShort = position.quantity < 0;
  const qtyColor = isShort ? DOWN : UP;
  const isOption = position.instrument === "call" || position.instrument === "put";
  const delta = position.greeks?.delta;

  return (
    <div
      className="grid items-center gap-2 px-2.5 py-2 rounded-lg group"
      style={{
        gridTemplateColumns: "auto 1fr auto auto",
        background: "var(--df-surface)",
        border: "1px solid var(--df-surface)",
      }}
    >
      {/* Instrument + symbol */}
      <span
        className="font-mono text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-md"
        style={instrumentStyle(position.instrument)}
      >
        {position.instrument === "equity" ? "EQ" : position.instrument.toUpperCase()}
      </span>

      <div className="min-w-0">
        <div className="font-mono text-xs font-semibold truncate" style={{ color: "var(--df-text)" }}>
          {position.symbol}
          {isOption && position.strike != null && (
            <span style={{ color: DIM }}> {position.strike}</span>
          )}
        </div>
        {isOption && position.expiry && (
          <div className="font-mono text-[9px]" style={{ color: MUTED }}>
            exp {position.expiry}
            {delta != null && (
              <>
                {" · "}
                <Explainable computation={position.wolfram} title={`${position.symbol} leg Δ`}>
                  <span style={{ color: delta >= 0 ? UP : DOWN }}>
                    Δ{delta >= 0 ? "+" : ""}
                    {delta.toFixed(2)}
                  </span>
                </Explainable>
              </>
            )}
          </div>
        )}
      </div>

      {/* Signed quantity */}
      <span className="font-mono text-xs font-semibold tabular-nums" style={{ color: qtyColor }}>
        {position.quantity > 0 ? "+" : ""}
        {position.quantity}
      </span>

      {/* Remove */}
      <button
        type="button"
        onClick={() => onRemove(position.id)}
        aria-label={`Remove ${position.symbol} position`}
        className="w-5 h-5 flex items-center justify-center rounded-md opacity-50 group-hover:opacity-100 transition-opacity"
        style={{ background: "var(--df-surface)", color: MUTED }}
      >
        ×
      </button>
    </div>
  );
}
