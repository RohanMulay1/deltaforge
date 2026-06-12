"use client";

/**
 * PnLSurfaceChart — the scenario P&L visualization (ARCHITECTURE.md §10.3, P2).
 * Renders the `ScenarioSurface.pnl_grid` (`[y][x]`, y=IV%, x=spot%) as a
 * terminal-palette heatmap: green = profit, red = loss, intensity ∝ |P&L|.
 * Beneath it, the spot-only P&L slice (the y-midpoint row) is drawn as a
 * Recharts line so the user reads the directional curve and breakeven.
 *
 * Color is semantic (up/down), not decorative — profit and loss are instantly
 * legible. Hovering a cell surfaces its exact P&L + the spot/IV shift.
 */

import { useMemo, useState } from "react";

import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ScenarioSurface } from "@/types";

interface PnLSurfaceChartProps {
  surface: ScenarioSurface;
}

const UP = "#05b169";
const DOWN = "#cf202f";
const MUTED = "var(--df-text-muted, #7c828a)";
const DIM = "var(--df-text-dim, #a8acb3)";

function cellColor(pnl: number, maxAbs: number): string {
  if (maxAbs <= 0) return "var(--df-surface)";
  const intensity = Math.min(Math.abs(pnl) / maxAbs, 1);
  const alpha = 0.08 + intensity * 0.62;
  return pnl >= 0
    ? `rgba(5,177,105,${alpha.toFixed(3)})`
    : `rgba(207,32,47,${alpha.toFixed(3)})`;
}

function pctLabel(frac: number): string {
  const pct = frac * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(0)}%`;
}

interface HoverCell {
  spotPct: number;
  ivPct: number;
  pnl: number;
}

export function PnLSurfaceChart({ surface }: PnLSurfaceChartProps) {
  const [hover, setHover] = useState<HoverCell | null>(null);

  const xValues = surface.x_axis.values;
  const yValues = surface.y_axis.values;
  const grid = surface.pnl_grid;

  const maxAbs = useMemo(() => {
    let m = 0;
    for (const row of grid) {
      for (const v of row) {
        m = Math.max(m, Math.abs(v));
      }
    }
    return m;
  }, [grid]);

  // Spot-only slice = the middle IV row (closest to no IV shift).
  const sliceData = useMemo(() => {
    if (grid.length === 0) return [];
    const midRow = Math.floor(grid.length / 2);
    const row = grid[midRow] ?? [];
    return xValues.map((x, i) => ({ spot: x * 100, pnl: row[i] ?? 0 }));
  }, [grid, xValues]);

  const hasGrid = grid.length > 0 && xValues.length > 0;

  return (
    <div className="space-y-4">
      {/* Heatmap */}
      {hasGrid ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: MUTED, letterSpacing: "0.1em" }}>
              P&L Surface — IV (rows) × Spot (cols)
            </span>
            {hover && (
              <span className="font-mono text-[10px] tabular-nums" style={{ color: hover.pnl >= 0 ? UP : DOWN }}>
                spot {pctLabel(hover.spotPct)} · iv {pctLabel(hover.ivPct)} → {hover.pnl >= 0 ? "+" : ""}
                {hover.pnl.toFixed(2)}
              </span>
            )}
          </div>

          <div
            className="grid gap-[2px]"
            style={{ gridTemplateColumns: `repeat(${xValues.length}, minmax(0, 1fr))` }}
            onMouseLeave={() => setHover(null)}
          >
            {grid.map((row, yi) =>
              row.map((pnl, xi) => (
                <div
                  key={`${yi}-${xi}`}
                  onMouseEnter={() =>
                    setHover({ spotPct: xValues[xi], ivPct: yValues[yi], pnl })
                  }
                  title={`spot ${pctLabel(xValues[xi])}, iv ${pctLabel(yValues[yi])}: ${pnl.toFixed(2)}`}
                  style={{
                    height: 16,
                    borderRadius: 2,
                    background: cellColor(pnl, maxAbs),
                    cursor: "crosshair",
                  }}
                />
              )),
            )}
          </div>

          <div className="flex items-center justify-between font-mono text-[9px]" style={{ color: MUTED }}>
            <span>{pctLabel(xValues[0])}</span>
            <span>spot move</span>
            <span>{pctLabel(xValues[xValues.length - 1])}</span>
          </div>
        </div>
      ) : (
        <div className="font-mono text-[11px]" style={{ color: MUTED }}>
          No grid — add positions to revalue a P&L surface.
        </div>
      )}

      {/* Spot-only slice line */}
      {sliceData.length > 0 && (
        <div style={{ height: 150 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sliceData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis
                dataKey="spot"
                tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
                tick={{ fill: "#7c828a", fontSize: 10, fontFamily: "var(--font-mono, monospace)" }}
                stroke="var(--df-border-strong)"
              />
              <YAxis
                tick={{ fill: "#7c828a", fontSize: 10, fontFamily: "var(--font-mono, monospace)" }}
                stroke="var(--df-border-strong)"
                width={44}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(13,15,19,0.96)",
                  border: "1px solid var(--df-border-strong)",
                  borderRadius: 8,
                  fontFamily: "var(--font-mono, monospace)",
                  fontSize: 11,
                }}
                labelFormatter={(v) => {
                  const n = Number(v)
                  return `spot ${n > 0 ? "+" : ""}${n.toFixed(0)}%`
                }}
                formatter={(v) => [Number(v).toFixed(2), "P&L"]}
              />
              <ReferenceLine y={0} stroke="var(--df-border-strong)" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="pnl" stroke="#f5a623" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
