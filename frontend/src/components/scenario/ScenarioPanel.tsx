"use client";

/**
 * ScenarioPanel — the P&L scenario surface (ARCHITECTURE.md §10.3, P2). Spot% /
 * IV% / DTE sliders drive a debounced POST /scenario (`useScenarioPnl`) →
 * `PnLSurfaceChart` heatmap + spot slice, with a headline base P&L, breakeven
 * spot, and a Wolfram-expression strip wrapped in `<Explainable>` so the user
 * can audit the symbolic P&L surface the kernel evaluated.
 *
 * The panel hedges to the rail's real positions; with none it shows an honest
 * "add positions" prompt instead of a faked surface.
 */

import { useState } from "react";

import { Explainable } from "@/components/explain/Explainable";
import { PnLSurfaceChart } from "@/components/scenario/PnLSurfaceChart";
import { ScenarioSliders } from "@/components/scenario/ScenarioSliders";
import { usePortfolio } from "@/hooks/usePortfolio";
import { useScenarioPnl, type ScenarioControls } from "@/hooks/useScenarioPnl";

const ACCENT = "var(--df-accent, #f5a623)";
const UP = "var(--df-up, #05b169)";
const DOWN = "var(--df-down, #cf202f)";
const MUTED = "var(--df-text-muted, #7c828a)";
const DIM = "var(--df-text-dim, #a8acb3)";

const DEFAULT_CONTROLS: ScenarioControls = {
  spotSpanPct: 15,
  spotStepPct: 3,
  ivSpanPct: 20,
  ivStepPct: 5,
  dteOverride: null,
};

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-xl px-3.5 py-2.5" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
      <div className="font-mono text-[9px] font-bold uppercase tracking-widest mb-1" style={{ color: MUTED }}>
        {label}
      </div>
      <div className="font-mono text-sm font-semibold tabular-nums" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

export function ScenarioPanel() {
  const { positions } = usePortfolio();
  const [controls, setControls] = useState<ScenarioControls>(DEFAULT_CONTROLS);

  const { surface, isFetching, isError, error, enabled } = useScenarioPnl(
    positions,
    controls,
  );

  const basePnl = surface?.base_pnl ?? 0;
  const breakeven = surface?.breakeven_spot;

  return (
    <div
      className="rounded-2xl px-5 py-4 space-y-4"
      style={{
        background: "rgba(16,18,22,0.70)",
        border: "1px solid var(--df-border, rgba(255,255,255,0.07))",
        backdropFilter: "blur(16px)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-[11px] font-bold tracking-widest uppercase text-white" style={{ letterSpacing: "0.1em" }}>
            Scenario P&L Surface
          </span>
          {surface && (
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full"
              style={
                surface.is_stub
                  ? { background: "rgba(244,176,0,0.12)", color: "var(--df-warn, #f4b000)", border: "1px solid rgba(244,176,0,0.30)" }
                  : { background: "rgba(245,166,35,0.12)", color: ACCENT, border: "1px solid rgba(245,166,35,0.28)" }
              }
            >
              {surface.is_stub ? "STUB" : "WOLFRAM TABLE"}
            </span>
          )}
        </div>
        {isFetching && (
          <span className="font-mono text-[9px]" style={{ color: MUTED }}>
            evaluating…
          </span>
        )}
      </div>

      <ScenarioSliders controls={controls} onChange={setControls} />

      {!enabled ? (
        <div
          className="rounded-xl px-4 py-8 text-center font-mono text-[11px]"
          style={{ border: "1px dashed rgba(255,255,255,0.10)", color: MUTED }}
        >
          Add positions in the rail to revalue a P&L surface across spot / IV / time.
        </div>
      ) : (
        <>
          {isError && error && (
            <div className="font-mono text-[10px]" style={{ color: DOWN }}>
              scenario unavailable: {error}
            </div>
          )}

          {surface && (
            <>
              {/* Headline metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                <Metric
                  label="Base P&L"
                  value={`${basePnl >= 0 ? "+" : ""}${basePnl.toFixed(2)}`}
                  color={basePnl >= 0 ? UP : DOWN}
                />
                <Metric
                  label="Breakeven Spot"
                  value={breakeven != null ? `$${breakeven.toFixed(2)}` : "—"}
                  color={DIM}
                />
                <Metric
                  label="Engine"
                  value={surface.wolfram.engine === "wolfram" ? "WOLFRAM" : "FALLBACK"}
                  color={surface.wolfram.engine === "wolfram" ? UP : "var(--df-warn, #f4b000)"}
                />
              </div>

              <PnLSurfaceChart surface={surface} />

              {/* WL expression strip */}
              <div
                className="rounded-xl px-3.5 py-3"
                style={{ background: "rgba(245,166,35,0.05)", border: "1px solid rgba(245,166,35,0.15)" }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: ACCENT, letterSpacing: "0.12em" }}>
                    Symbolic P&L Expression
                  </span>
                  <Explainable computation={surface.wolfram} title="Scenario P&L Surface">
                    <span className="font-mono text-[9px] font-bold uppercase" style={{ color: DIM }}>
                      audit
                    </span>
                  </Explainable>
                </div>
                <div className="font-mono text-[10px] leading-relaxed break-all" style={{ color: DIM }}>
                  {surface.wolfram.expression}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
