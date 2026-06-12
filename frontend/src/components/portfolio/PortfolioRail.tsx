"use client";

/**
 * PortfolioRail — the left rail (ARCHITECTURE.md §10.3). Composes:
 *   aggregate Greeks header (kernel-verified) · virtualized positions list ·
 *   add-position ticket · tolerant CSV-paste import · disclaimer footer.
 *
 * State is client-side (`usePortfolio`); aggregate Greeks come from a debounced
 * POST /portfolio/greeks (`usePortfolioGreeks`). The rail lifts its real
 * `portfolio_greeks` up via `onGreeksChange` so the HedgePanel can hedge the
 * actual delta (kills the all-zero mock path).
 */

import { useEffect } from "react";

import { AddPositionTicket } from "@/components/portfolio/AddPositionTicket";
import { AggregateGreeks } from "@/components/portfolio/AggregateGreeks";
import { CsvPasteImport } from "@/components/portfolio/CsvPasteImport";
import { PositionsList } from "@/components/portfolio/PositionsList";
import { usePortfolio } from "@/hooks/usePortfolio";
import { usePortfolioGreeks } from "@/hooks/usePortfolioGreeks";
import type { PortfolioGreeks } from "@/types";

interface PortfolioRailProps {
  /** Fallback symbol (e.g. the analyzed ticker) when the rail is empty. */
  fallbackSymbol?: string | null;
  dteMax?: number;
  /** Lifts the rail's real aggregate Greeks up (HedgePanel consumes delta). */
  onGreeksChange?: (greeks: PortfolioGreeks | undefined) => void;
}

const DISCLAIMER = "Informational only. Not investment advice. No live execution.";
const MUTED = "var(--df-text-muted, #7c828a)";

export function PortfolioRail({
  fallbackSymbol = null,
  dteMax = 7,
  onGreeksChange,
}: PortfolioRailProps) {
  const { positions, add, addMany, remove, primarySymbol } = usePortfolio();
  const symbol = primarySymbol ?? fallbackSymbol;

  const { greeks, isFetching, isError, error } = usePortfolioGreeks(
    positions,
    symbol,
    dteMax,
  );

  // Lift the aggregate up for the hedge panel (effect avoids render-phase calls).
  useEffect(() => {
    onGreeksChange?.(greeks);
  }, [greeks, onGreeksChange]);

  const isEmpty = positions.length === 0;

  return (
    <div className="flex flex-col gap-4 sticky top-[72px]">
      <div
        className="rounded-2xl px-4 py-4 flex flex-col gap-4"
        style={{
          background: "rgba(16,18,22,0.72)",
          border: "1px solid var(--df-border, rgba(255,255,255,0.07))",
          backdropFilter: "blur(16px)",
        }}
      >
        <AggregateGreeks greeks={greeks} isFetching={isFetching} isEmpty={isEmpty} />

        {isError && error && (
          <div className="font-mono text-[10px]" style={{ color: "var(--df-down, #cf202f)" }}>
            greeks unavailable: {error}
          </div>
        )}

        <div style={{ height: 1, background: "rgba(255,255,255,0.06)" }} />

        <PositionsList positions={positions} onRemove={remove} />

        <div style={{ height: 1, background: "rgba(255,255,255,0.06)" }} />

        <AddPositionTicket onAdd={add} />

        <CsvPasteImport onImport={addMany} />

        <div
          className="font-mono text-[9px] leading-relaxed pt-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)", color: MUTED }}
        >
          {DISCLAIMER}
        </div>
      </div>
    </div>
  );
}
