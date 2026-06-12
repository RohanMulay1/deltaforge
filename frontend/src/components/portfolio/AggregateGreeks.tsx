"use client";

/**
 * AggregateGreeks — the rail header showing kernel-verified portfolio Greeks
 * (ARCHITECTURE.md §10.3). Net delta is emphasized (it is what the hedge
 * neutralizes); Γ Θ V sit beneath. The whole aggregate is wrapped in a single
 * `<Explainable>` so a click reveals the exact `Total[bsGreeks @@@ book]` WL
 * expression that produced it.
 */

import { Explainable } from "@/components/explain/Explainable";
import type { PortfolioGreeks } from "@/types";

interface AggregateGreeksProps {
  greeks: PortfolioGreeks | undefined;
  isFetching: boolean;
  isEmpty: boolean;
}

const ACCENT = "var(--df-accent, #f5a623)";
const MUTED = "var(--df-text-muted, #7c828a)";

function signColor(value: number): string {
  if (value > 0) return "var(--df-up, #05b169)";
  if (value < 0) return "var(--df-down, #cf202f)";
  return "var(--df-text, #fff)";
}

function fmt(value: number, digits = 3): string {
  const s = value.toFixed(digits);
  return value > 0 ? `+${s}` : s;
}

function MiniGreek({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="rounded-xl px-2.5 py-2"
      style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}
    >
      <div className="font-mono text-[9px] font-bold uppercase tracking-widest mb-1" style={{ color: MUTED }}>
        {label}
      </div>
      <div className="font-mono text-xs font-semibold tabular-nums" style={{ color: signColor(value) }}>
        {fmt(value)}
      </div>
    </div>
  );
}

export function AggregateGreeks({ greeks, isFetching, isEmpty }: AggregateGreeksProps) {
  const netDelta = greeks?.delta ?? 0;
  const netDollars = greeks?.net_delta_dollars ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: ACCENT, letterSpacing: "0.14em" }}>
          Portfolio Greeks
        </span>
        {isFetching && (
          <span className="font-mono text-[9px]" style={{ color: MUTED }}>
            computing…
          </span>
        )}
      </div>

      {/* Net delta emphasis */}
      <div
        className="rounded-2xl px-4 py-3.5"
        style={{ background: "rgba(245,166,35,0.06)", border: "1px solid rgba(245,166,35,0.18)" }}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: ACCENT }}>
            Net Δ
          </span>
          <span className="font-mono text-[9px]" style={{ color: MUTED }}>
            Δ$ {netDollars.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        </div>
        <Explainable computation={greeks?.wolfram} title="Portfolio Delta — Total[bsGreeks @@@ book]">
          <span
            className="font-mono text-2xl font-semibold tabular-nums"
            style={{ color: isEmpty ? MUTED : signColor(netDelta) }}
          >
            {isEmpty ? "—" : fmt(netDelta)}
          </span>
        </Explainable>
      </div>

      {/* Γ Θ V */}
      <div className="grid grid-cols-3 gap-2">
        <MiniGreek label="Γ Gamma" value={greeks?.gamma ?? 0} />
        <MiniGreek label="Θ Theta" value={greeks?.theta ?? 0} />
        <MiniGreek label="V Vega" value={greeks?.vega ?? 0} />
      </div>

      {isEmpty && (
        <div className="font-mono text-[10px]" style={{ color: MUTED }}>
          Add positions to compute aggregate exposure.
        </div>
      )}
    </div>
  );
}
