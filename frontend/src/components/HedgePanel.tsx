"use client";

import { Explainable } from "@/components/explain/Explainable";
import type { HedgeRecommendation } from "@/types";

interface HedgePanelProps {
  hedge: HedgeRecommendation;
}

export default function HedgePanel({ hedge }: HedgePanelProps) {
  const [pnlMin, pnlMax] = hedge.expected_pnl_range;
  const range = pnlMax - pnlMin;
  const zeroFraction = range > 0 ? Math.max(0, Math.min(1, (0 - pnlMin) / range)) : 0.5;
  const zeroPercent = (zeroFraction * 100).toFixed(1);
  const isCall = hedge.option_type_to_trade === "call";

  return (
    <div className="cb-card overflow-hidden cursor-default">
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: "1px solid var(--df-border)" }}
      >
        <span className="text-[11px] font-bold tracking-widest uppercase text-white" style={{ letterSpacing: "0.1em" }}>
          OPTIMAL DELTA-NEUTRAL HEDGE
        </span>
        <span
          className="font-mono text-[9px] font-bold tracking-widest uppercase px-2.5 py-1 rounded-full"
          style={{
            background: "rgba(245,166,35,0.14)",
            color: "#f5a623",
            border: "1px solid rgba(245,166,35,0.28)",
            letterSpacing: "0.08em",
          }}
        >
          WOLFRAM NMINIMIZE
        </span>
      </div>

      <div className="px-5 py-4 space-y-4">
        {/* Wolfram expression — click to audit the exact NMinimize provenance */}
        <div
          className="rounded-2xl p-4"
          style={{ background: "rgba(245,166,35,0.05)", border: "1px solid rgba(245,166,35,0.15)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-widest"
              style={{ color: "#f5a623", letterSpacing: "0.12em" }}
            >
              SYMBOLIC COMPUTATION
            </span>
            <Explainable computation={hedge.wolfram} title="Delta-Neutral Hedge — NMinimize">
              <span className="font-mono text-[9px] font-bold uppercase" style={{ color: "#a8acb3" }}>
                audit
              </span>
            </Explainable>
          </div>
          <div className="font-mono text-[11px] leading-relaxed break-all" style={{ color: "#a8acb3" }}>
            {hedge.wolfram_computation_used}
          </div>
        </div>

        {/* 4-metric grid */}
        <div className="grid grid-cols-2 gap-2.5">
          {[
            { label: "DELTA RATIO", value: hedge.delta_neutral_ratio.toFixed(4), color: "#f5a623", explain: true },
            { label: "CONTRACTS",   value: String(hedge.contracts_to_trade),       color: "var(--df-text)", explain: false },
          ].map(({ label, value, color, explain }) => (
            <div
              key={label}
              className="rounded-2xl p-3.5 transition-all"
              style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}
            >
              <div className="font-mono text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "#7c828a" }}>
                {label}
              </div>
              {explain ? (
                <Explainable computation={hedge.wolfram} title="Delta-Neutral Ratio">
                  <span className="font-mono text-sm font-semibold tabular-nums" style={{ color }}>
                    {value}
                  </span>
                </Explainable>
              ) : (
                <div className="font-mono text-sm font-semibold tabular-nums" style={{ color }}>
                  {value}
                </div>
              )}
            </div>
          ))}

          {/* Type */}
          <div
            className="rounded-2xl p-3.5"
            style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}
          >
            <div className="font-mono text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "#7c828a" }}>
              TYPE
            </div>
            <span
              className="font-mono text-[10px] font-bold uppercase px-2.5 py-1 rounded-full"
              style={
                isCall
                  ? { background: "rgba(245,166,35,0.14)", color: "#f5a623", border: "1px solid rgba(245,166,35,0.28)" }
                  : { background: "rgba(207,32,47,0.12)", color: "#cf202f", border: "1px solid rgba(207,32,47,0.28)" }
              }
            >
              {hedge.option_type_to_trade.toUpperCase()}
            </span>
          </div>

          {/* Strike */}
          <div
            className="rounded-2xl p-3.5"
            style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}
          >
            <div className="font-mono text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: "#7c828a" }}>
              STRIKE
            </div>
            <div className="font-mono text-sm font-semibold tabular-nums text-white">
              ${hedge.strike_to_trade.toFixed(0)}
            </div>
          </div>
        </div>

        {/* P&L range */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-widest" style={{ color: "#7c828a" }}>
              EXPECTED P&L RANGE
            </span>
            <span className="font-mono text-[10px] tabular-nums" style={{ color: "#a8acb3" }}>
              <span style={{ color: "#cf202f" }}>{pnlMin.toFixed(2)}</span>
              {" / "}
              <span style={{ color: "#05b169" }}>+{pnlMax.toFixed(2)}</span>
            </span>
          </div>
          <div
            style={{
              position: "relative",
              height: 8,
              borderRadius: 100,
              background: "linear-gradient(to right, rgba(207,32,47,0.30), var(--df-border) 40%, var(--df-border) 60%, rgba(5,177,105,0.30))",
              border: "1px solid var(--df-border)",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: -5,
                bottom: -5,
                left: `${zeroPercent}%`,
                width: 2,
                background: "var(--df-border-strong)",
                borderRadius: 1,
                transform: "translateX(-50%)",
              }}
            />
          </div>
          <div className="flex justify-between mt-2">
            <span className="font-mono text-[9px]" style={{ color: "#cf202f" }}>{pnlMin.toFixed(2)}</span>
            <span className="font-mono text-[9px]" style={{ color: "#7c828a" }}>$0</span>
            <span className="font-mono text-[9px]" style={{ color: "#05b169" }}>+{pnlMax.toFixed(2)}</span>
          </div>
        </div>

        {/* Reasoning */}
        <div
          className="font-mono text-xs leading-relaxed pt-3"
          style={{ borderTop: "1px solid var(--df-border)", color: "#a8acb3" }}
        >
          {hedge.reasoning}
        </div>
      </div>
    </div>
  );
}
