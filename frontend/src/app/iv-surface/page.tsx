"use client"

import Link from "next/link"

import { Header } from "@/components/Header"
import IVSurfacePlot from "@/components/IVSurfacePlot"
import { EmptyState } from "@/components/feedback/EmptyState"
import { CardSkeleton } from "@/components/feedback/Skeleton"
import { useAnalysisStreamContext } from "@/components/analysis/AnalysisStreamProvider"

// Animated background — orbs + grain (matches the dashboard surface).
function SiteBg() {
  return (
    <>
      <div className="site-bg">
        <div className="site-bg-orb3" />
      </div>
      <div className="site-grain" />
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="term-label">{label}</span>
      <span className="font-mono text-sm font-bold tabular-nums" style={{ color: "var(--df-text,#e9ebee)" }}>
        {value}
      </span>
    </div>
  )
}

export default function IVSurfacePage() {
  const stream = useAnalysisStreamContext()
  const { partial, isStreaming } = stream

  const chain = partial?.options_chain ?? []
  const symbol = partial?.symbol ?? stream.symbol ?? "—"
  const spot = partial?.spot_price ?? 0
  const ivRank = partial?.iv_rank ?? null

  return (
    <div className="min-h-screen relative" style={{ background: "var(--df-bg)" }}>
      <SiteBg />
      <div className="relative z-10">
        <Header />

        <main className="max-w-[1200px] mx-auto px-4 sm:px-5 py-6 flex flex-col gap-5">
          {/* Title row */}
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div className="flex flex-col gap-1">
              <div className="term-label" style={{ color: "var(--df-accent,#f5a623)" }}>
                ◢ implied volatility
              </div>
              <h1 className="font-mono text-2xl sm:text-3xl font-bold" style={{ color: "var(--df-text,#e9ebee)", letterSpacing: "-0.5px" }}>
                IV Surface <span style={{ color: "var(--df-text-muted,#616773)" }}>—</span>{" "}
                <span style={{ color: "var(--df-accent,#f5a623)" }}>Wolfram Calibration</span>
              </h1>
              <p className="text-sm" style={{ color: "var(--df-text-dim,#9aa1ab)" }}>
                Per-strike implied vol from the symbolic kernel, sized by open interest.
              </p>
            </div>

            {chain.length > 0 && (
              <div className="flex items-center gap-6">
                <Stat label="Symbol" value={symbol} />
                <Stat label="Spot" value={spot ? `$${spot.toFixed(2)}` : "—"} />
                <Stat label="IV Rank" value={ivRank !== null ? `${(ivRank * 100).toFixed(0)}%` : "—"} />
                <Stat label="Contracts" value={String(chain.length)} />
              </div>
            )}
          </div>

          {/* Surface */}
          {chain.length > 0 ? (
            <IVSurfacePlot options={chain} height={480} />
          ) : isStreaming ? (
            <CardSkeleton height={480} />
          ) : (
            <div
              className="rounded-[10px] px-6 py-12"
              style={{ background: "var(--df-panel)", border: "1px solid var(--df-border)" }}
            >
              <EmptyState
                title="No analysis loaded"
                hint="Run an analysis on the dashboard to populate the IV surface."
              />
              <div className="flex justify-center mt-5">
                <Link
                  href="/"
                  className="font-mono text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-md transition-all"
                  style={{
                    background: "var(--df-accent-soft, rgba(245,166,35,0.12))",
                    border: "1px solid rgba(245,166,35,0.40)",
                    color: "var(--df-accent,#f5a623)",
                  }}
                >
                  ← Go to dashboard
                </Link>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
