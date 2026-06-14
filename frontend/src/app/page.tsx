"use client"

import { useState } from "react"

import { Header } from "@/components/Header"
import { HUDCards } from "@/components/HUDCards"
import { OptionsChainTable } from "@/components/OptionsChainTable"
import HedgePanel from "@/components/HedgePanel"
import AnalyzeForm from "@/components/AnalyzeForm"
import { PanelState } from "@/components/feedback/PanelState"
import { EmptyState } from "@/components/feedback/EmptyState"
import {
  CardSkeleton,
  ChainSkeleton,
  HudCardSkeleton,
} from "@/components/feedback/Skeleton"
import { PortfolioRail } from "@/components/portfolio/PortfolioRail"
import { ScenarioPanel } from "@/components/scenario/ScenarioPanel"
import { ExplainProvider } from "@/components/explain/ExplainContext"
import { ExplainDrawer } from "@/components/explain/ExplainDrawer"
import { ThemeToggle } from "@/components/ThemeToggle"
import { DeltaTerminal } from "@/components/DeltaTerminal"
import { useAnalysisStreamContext } from "@/components/analysis/AnalysisStreamProvider"
import { usePanelStatus } from "@/hooks/usePanelStatus"
import type { HedgeRecommendation, PortfolioGreeks } from "@/types"

// Animated background — orbs + grain
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

const DISCLAIMER = "Informational only. Not investment advice. No live execution."

const QUICK_PICKS = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "AMD"]

function QuickPicks({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex items-center justify-center gap-2 flex-wrap">
      {QUICK_PICKS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className="font-mono text-xs font-bold uppercase tracking-wider px-3 py-1.5 rounded-full transition-all hover:scale-[1.04]"
          style={{ background: "var(--df-surface)", border: "1px solid var(--df-border-strong)", color: "var(--df-text-dim,#a8acb3)" }}
        >
          {s}
        </button>
      ))}
    </div>
  )
}

export default function Home() {
  const stream = useAnalysisStreamContext()
  const { partial, stages, isStreaming, error } = stream
  const hasError = error !== null
  const hasStarted = stream.symbol !== null

  // The PortfolioRail lifts its real, kernel-verified aggregate Greeks up so the
  // HedgePanel hedges the actual portfolio delta (kills the all-zero mock path).
  const [railGreeks, setRailGreeks] = useState<PortfolioGreeks | undefined>(
    undefined,
  )

  // Per-panel 4-state derived from the stream's stage map (§10.1).
  const hudStatus = usePanelStatus(stages, "greeks", hasError)
  const marketStatus = usePanelStatus(stages, "market_data", hasError)
  const hedgeStatus = usePanelStatus(stages, "hedge", hasError)
  const summaryStatus = usePanelStatus(stages, "summary", hasError)

  const handleAnalyze = (symbol: string, dteMax: number) => stream.start(symbol, dteMax)

  // ── Landing view (no analysis yet) ──────────────────────────────────────
  if (!hasStarted) {
    return (
      <main className="relative min-h-screen overflow-hidden" style={{ background: "var(--df-bg, var(--df-bg))" }}>
        <SiteBg />
        {/* Minimal top bar — wordmark + theme toggle (the landing has no Header) */}
        <div
          className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-5"
          style={{ height: 52, borderBottom: "1px solid var(--df-border)" }}
        >
          <span className="font-mono text-[14px] font-bold tracking-tight" style={{ color: "var(--df-text)" }}>
            DELTA<span style={{ color: "var(--df-accent)" }}>FORGE</span>
          </span>
          <ThemeToggle />
        </div>
        <div className="relative z-10 flex min-h-screen items-center justify-center px-4 sm:px-6 pt-20 pb-12">
          <div className="w-full max-w-5xl flex flex-col items-center">

            {/* Centered headline */}
            <div className="flex flex-col items-center text-center mb-9">
              <div className="term-label mb-4" style={{ color: "var(--df-accent,#f5a623)" }}>
                ◢ options risk terminal
              </div>
              <h1
                className="font-mono text-6xl sm:text-7xl font-bold mb-4"
                style={{ color: "var(--df-text,#e9ebee)", letterSpacing: "-2.5px", lineHeight: 1 }}
              >
                DELTA<span style={{ color: "var(--df-accent, #f5a623)" }}>FORGE</span>
              </h1>
              <p className="text-base tracking-wide max-w-md mx-auto leading-relaxed" style={{ color: "var(--df-text-dim, #9aa1ab)" }}>
                Options risk &amp; delta-neutral hedging, computed by a real Wolfram kernel.
                <br />
                <span className="text-sm" style={{ color: "var(--df-text-muted,#616773)" }}>Symbolic math doesn&apos;t hallucinate. </span>
                <span className="text-sm" style={{ color: "var(--df-accent, #f5a623)" }}>It computes.</span>
              </p>
            </div>

            {/* Balanced two-up: action card | streaming terminal (equal height) */}
            <div className="w-full grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
              {/* Action card */}
              <div
                className="px-6 py-6 rounded-2xl flex flex-col justify-center gap-4"
                style={{ background: "var(--df-panel)", border: "1px solid var(--df-border-strong)", boxShadow: "0 20px 50px rgba(0,0,0,0.28)" }}
              >
                <div className="w-full">
                  <div className="term-label mb-2.5">Choose an underlying</div>
                  <AnalyzeForm onAnalyze={handleAnalyze} isStreaming={isStreaming} error={error} />
                </div>
                <div className="w-full pt-1 flex flex-col gap-2.5">
                  <span className="term-label">Or jump straight in</span>
                  <QuickPicks onPick={(s) => handleAnalyze(s, 7)} />
                </div>
              </div>

              {/* Streaming terminal — stretches to match the card height */}
              <DeltaTerminal />
            </div>

          </div>
        </div>
      </main>
    )
  }

  // ── Dashboard view — stream-driven shell [Rail | Main | Scenario] ────────
  const chain = partial?.options_chain ?? []
  const spotPrice = partial?.spot_price ?? 0
  const symbol = partial?.symbol ?? stream.symbol ?? "–"

  // HedgePanel consumes the rail's real portfolio_greeks.delta when the user has
  // positions; otherwise it renders the stream's hedge as-is.
  const streamHedge = partial?.hedge ?? null
  const hedge: HedgeRecommendation | null =
    streamHedge && railGreeks
      ? {
          ...streamHedge,
          current_portfolio_delta: railGreeks.delta,
          residual_delta_after_hedge:
            streamHedge.delta_target - railGreeks.delta,
        }
      : streamHedge

  return (
    <ExplainProvider>
    <div className="min-h-screen relative" style={{ background: "var(--df-bg, var(--df-bg))" }}>
      <SiteBg />

      <div className="relative z-10">
        <Header />

        {/* Shell grid: [PortfolioRail(300px) | Main(minmax(0,1fr))]; ScenarioPanel below. */}
        <main className="max-w-[1720px] mx-auto px-4 sm:px-5 py-4 grid gap-4 grid-cols-1 lg:grid-cols-[290px_minmax(0,1fr)]">
          {/* ── PortfolioRail (left, full height) ─────────────────────────── */}
          <aside data-slot="portfolio-rail" className="hidden lg:block">
            <PortfolioRail
              fallbackSymbol={stream.symbol}
              dteMax={stream.dteMax ?? 7}
              onGreeksChange={setRailGreeks}
            />
          </aside>

          {/* ── Main column ─────────────────────────────────────────────── */}
          <div className="flex flex-col gap-4 min-w-0">
            <div
              className="rounded-[10px] px-5 py-3.5 flex items-center justify-between gap-4 flex-wrap"
              style={{ background: "var(--df-panel, var(--df-panel))", border: "1px solid var(--df-border, var(--df-border))" }}
            >
              <AnalyzeForm
                onAnalyze={handleAnalyze}
                isStreaming={isStreaming}
                error={error}
                initialSymbol={stream.symbol ?? "SPY"}
                initialDteMax={stream.dteMax ?? 7}
                compact
              />
              <div className="hidden xl:flex items-center gap-1.5">
                <span className="term-label mr-1">Switch</span>
                {QUICK_PICKS.slice(0, 5).map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={isStreaming}
                    onClick={() => handleAnalyze(s, stream.dteMax ?? 7)}
                    className="font-mono text-[11px] font-bold uppercase tracking-wider px-2.5 py-1.5 rounded-md transition-all"
                    style={{
                      background: symbol === s ? "var(--df-accent-soft, rgba(245,166,35,0.12))" : "var(--df-surface)",
                      border: `1px solid ${symbol === s ? "rgba(245,166,35,0.45)" : "var(--df-border-strong)"}`,
                      color: symbol === s ? "var(--df-accent,#f5a623)" : "var(--df-text-dim,#9aa1ab)",
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* HUD cards (greeks stage) */}
            <PanelState
              status={hudStatus}
              errorMessage={error}
              emptyTitle="Greeks pending"
              skeleton={
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <HudCardSkeleton key={i} />
                  ))}
                </div>
              }
            >
              {partial?.portfolio_greeks && (
                <HUDCards
                  spotPrice={spotPrice}
                  expiry={partial.expiry ?? "—"}
                  ivRank={partial.iv_rank ?? 0}
                  greeks={partial.portfolio_greeks}
                />
              )}
            </PanelState>

            <div style={{ height: 1, background: "var(--df-surface)" }} />

            {/* Two balanced stacks: [chain + scenario] | [iv + hedge + summary].
                Keeping both columns as multi-panel flex stacks tessellates the
                space — no full-width band and no sparse gap under the chain. */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
              {/* Left stack */}
              <div className="lg:col-span-2 min-w-0 flex flex-col gap-4">
                <PanelState
                  status={marketStatus}
                  errorMessage={error}
                  emptyTitle="Chain pending"
                  emptyHint="Run an analysis to load the options chain"
                  skeleton={<ChainSkeleton rows={10} />}
                >
                  {chain.length > 0 ? (
                    <OptionsChainTable rows={chain} spotPrice={spotPrice} symbol={symbol} />
                  ) : (
                    <EmptyState title="No chain data" hint="Provider returned an empty chain" />
                  )}
                </PanelState>

                <section data-slot="scenario-panel">
                  <ScenarioPanel />
                </section>
              </div>

              {/* Right stack */}
              <div className="flex flex-col gap-4 min-w-0">
                <PanelState
                  status={hedgeStatus}
                  errorMessage={error}
                  emptyTitle="Hedge pending"
                  skeleton={<CardSkeleton height={260} />}
                >
                  {hedge && <HedgePanel hedge={hedge} />}
                </PanelState>

                <PanelState
                  status={summaryStatus}
                  errorMessage={error}
                  emptyTitle="Narrative pending"
                  skeleton={<CardSkeleton height={120} />}
                >
                  {partial?.risk_summary && (
                    <div
                      className="rounded-[10px] px-5 py-4 flex-1"
                      style={{ background: "linear-gradient(160deg, rgba(245,166,35,0.05), var(--df-panel,var(--df-panel)))", border: "1px solid var(--df-border, var(--df-border))" }}
                    >
                      <div className="flex items-center gap-2 mb-2.5">
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--df-accent,#f5a623)" }} />
                        <span className="term-label">Risk Summary · Groq LLaMA</span>
                      </div>
                      <p className="font-mono text-xs leading-relaxed" style={{ color: "var(--df-text-dim, #9aa1ab)" }}>
                        {partial.risk_summary}
                      </p>
                    </div>
                  )}
                </PanelState>
              </div>
            </div>

            {/* Footer + disclaimer (§12) */}
            <div
              className="flex items-center justify-between font-mono text-[10px] pt-3 pb-5"
              style={{ borderTop: "1px solid var(--df-border, var(--df-border))", color: "var(--df-text-muted, #616773)" }}
            >
              <span>{DISCLAIMER}</span>
              <span style={{ color: "var(--df-accent, #f5a623)", fontWeight: 700, letterSpacing: "0.05em" }}>DF</span>
            </div>
          </div>
        </main>
      </div>

      {/* ── Shared explain-drawer overlay (one per app) ──────────────────── */}
      <ExplainDrawer />
    </div>
    </ExplainProvider>
  )
}
