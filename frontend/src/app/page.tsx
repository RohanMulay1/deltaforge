"use client"

import { useState, type ReactNode } from "react"

import AnalyzeForm from "@/components/AnalyzeForm"
import HedgePanel from "@/components/HedgePanel"
import { Header } from "@/components/Header"
import { HUDCards } from "@/components/HUDCards"
import IVSurfacePlot from "@/components/IVSurfacePlot"
import { OptionsChainTable } from "@/components/OptionsChainTable"
import { EmptyState } from "@/components/feedback/EmptyState"
import { PanelState } from "@/components/feedback/PanelState"
import {
  CardSkeleton,
  ChainSkeleton,
  HudCardSkeleton,
} from "@/components/feedback/Skeleton"
import { ExplainDrawer } from "@/components/explain/ExplainDrawer"
import { ExplainProvider } from "@/components/explain/ExplainContext"
import { PortfolioRail } from "@/components/portfolio/PortfolioRail"
import { ScenarioPanel } from "@/components/scenario/ScenarioPanel"
import { useAnalysisStream } from "@/hooks/useAnalysisStream"
import { usePanelStatus } from "@/hooks/usePanelStatus"
import type { HedgeRecommendation, PortfolioGreeks } from "@/types"

function SiteBg() {
  return (
    <>
      <div className="site-bg" />
      <div className="site-grain" />
    </>
  )
}

const DISCLAIMER = "Informational only. Not investment advice. No live execution."

const QUICK_PICKS = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "AMD"]

const TICKER_RIBBON = [
  { symbol: "SPY", price: "643.28", move: "+0.34%", up: true },
  { symbol: "QQQ", price: "552.91", move: "-0.18%", up: false },
  { symbol: "NVDA", price: "191.42", move: "+1.12%", up: true },
  { symbol: "AAPL", price: "214.09", move: "+0.08%", up: true },
  { symbol: "TSLA", price: "181.77", move: "-0.71%", up: false },
  { symbol: "AMD", price: "162.36", move: "+0.45%", up: true },
]

const HERO_METRICS = [
  { label: "Kernel latency", value: "184ms" },
  { label: "Chain depth", value: "240 rows" },
  { label: "Risk model", value: "BS + NMin" },
  { label: "Execution", value: "Read-only" },
]

const DESK_ROWS = [
  { strike: "640C", bid: "7.18", ask: "7.26", delta: "+0.537", vol: "18.2K" },
  { strike: "642C", bid: "6.04", ask: "6.12", delta: "+0.491", vol: "14.7K" },
  { strike: "645P", bid: "5.82", ask: "5.91", delta: "-0.462", vol: "22.6K" },
  { strike: "647P", bid: "6.88", ask: "6.99", delta: "-0.508", vol: "11.3K" },
]

const ORDER_BOOK = [
  { bid: "7.18", bsz: "1,240", ask: "7.26", asz: "980" },
  { bid: "7.16", bsz: "860", ask: "7.28", asz: "1,410" },
  { bid: "7.14", bsz: "1,720", ask: "7.31", asz: "640" },
  { bid: "7.11", bsz: "940", ask: "7.33", asz: "1,180" },
]

function QuickPicks({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {QUICK_PICKS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className="rounded-sm px-2.5 py-1.5 font-mono text-[11px] font-bold uppercase transition-colors"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--df-border-strong)",
            color: "var(--df-text-dim,#a8acb3)",
          }}
        >
          {s}
        </button>
      ))}
    </div>
  )
}

function PanelShell({
  title,
  action,
  children,
  className = "",
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`terminal-panel min-w-0 ${className}`}>
      <div className="terminal-panel-head">
        <span>{title}</span>
        {action}
      </div>
      {children}
    </section>
  )
}

function TickerRibbon() {
  return (
    <div className="border-y border-[var(--df-border)] bg-[var(--df-panel)]">
      <div className="mx-auto flex max-w-[1720px] overflow-hidden px-4">
        <div className="flex min-w-max items-center gap-6 py-2">
          {TICKER_RIBBON.concat(TICKER_RIBBON).map((t, i) => (
            <div key={`${t.symbol}-${i}`} className="flex items-center gap-2 font-mono text-[11px]">
              <span className="font-bold text-[var(--df-text)]">{t.symbol}</span>
              <span className="tabular-nums text-[var(--df-text-dim)]">{t.price}</span>
              <span
                className="tabular-nums font-semibold"
                style={{ color: t.up ? "var(--df-up)" : "var(--df-down)" }}
              >
                {t.move}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MiniBook() {
  return (
    <div className="grid gap-1 px-3 py-3">
      <div className="grid grid-cols-4 border-b border-[var(--df-border)] pb-1 font-mono text-[9px] font-bold uppercase text-[var(--df-text-muted)]">
        <span>Bid</span>
        <span className="text-right">Size</span>
        <span className="text-right">Ask</span>
        <span className="text-right">Size</span>
      </div>
      {ORDER_BOOK.map((row) => (
        <div key={`${row.bid}-${row.ask}`} className="grid grid-cols-4 font-mono text-[11px] tabular-nums">
          <span className="font-semibold text-[var(--df-up)]">{row.bid}</span>
          <span className="text-right text-[var(--df-text-dim)]">{row.bsz}</span>
          <span className="text-right font-semibold text-[var(--df-down)]">{row.ask}</span>
          <span className="text-right text-[var(--df-text-dim)]">{row.asz}</span>
        </div>
      ))}
    </div>
  )
}

export default function Home() {
  const stream = useAnalysisStream()
  const { partial, stages, isStreaming, error } = stream
  const hasError = error !== null
  const hasStarted = stream.symbol !== null

  const [railGreeks, setRailGreeks] = useState<PortfolioGreeks | undefined>(undefined)

  const hudStatus = usePanelStatus(stages, "greeks", hasError)
  const marketStatus = usePanelStatus(stages, "market_data", hasError)
  const ivStatus = usePanelStatus(stages, "iv_surface", hasError)
  const hedgeStatus = usePanelStatus(stages, "hedge", hasError)
  const summaryStatus = usePanelStatus(stages, "summary", hasError)

  const handleAnalyze = (symbol: string, dteMax: number) => stream.start(symbol, dteMax)

  if (!hasStarted) {
    return (
      <main className="relative min-h-screen overflow-hidden" style={{ background: "var(--df-bg, #0a0b0d)" }}>
        <SiteBg />
        <div className="relative z-10">
          <TickerRibbon />
          <div className="mx-auto grid min-h-[calc(100vh-34px)] max-w-[1720px] grid-cols-1 gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_520px]">
            <section className="terminal-panel flex min-h-[560px] flex-col justify-between p-4 sm:p-6">
              <div>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <span className="term-label text-[var(--df-accent)]">Options risk terminal</span>
                  <span className="h-1 w-1 rounded-full bg-[var(--df-text-muted)]" />
                  <span className="font-mono text-[10px] font-bold uppercase text-[var(--df-up)]">Live market data</span>
                  <span className="font-mono text-[10px] font-bold uppercase text-[var(--df-text-muted)]">No execution</span>
                </div>
                <h1 className="max-w-4xl text-4xl font-semibold leading-[0.98] tracking-normal text-[var(--df-text)] sm:text-6xl lg:text-7xl">
                  Symbolic options risk, laid out like a trading desk.
                </h1>
                <p className="mt-5 max-w-2xl text-sm leading-6 text-[var(--df-text-dim)] sm:text-base">
                  Analyze chains, Greeks, IV surface, hedge recommendations, and portfolio exposure in a single dense workspace powered by a real Wolfram kernel.
                </p>
              </div>

              <div className="mt-8 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
                <div className="terminal-panel bg-[var(--df-panel-2)] p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="term-label">Launch dashboard</span>
                    <span className="font-mono text-[10px] font-bold uppercase text-[var(--df-text-muted)]">DTE + symbol</span>
                  </div>
                  <AnalyzeForm onAnalyze={handleAnalyze} isStreaming={isStreaming} error={error} />
                </div>
                <div className="terminal-panel bg-[var(--df-panel-2)] p-3">
                  <div className="mb-2 term-label">Fast markets</div>
                  <QuickPicks onPick={(s) => handleAnalyze(s, 7)} />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
                {HERO_METRICS.map((m) => (
                  <div key={m.label} className="terminal-panel px-3 py-2">
                    <div className="term-label mb-1">{m.label}</div>
                    <div className="font-mono text-sm font-semibold tabular-nums text-[var(--df-text)]">{m.value}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="grid min-h-[560px] grid-rows-[auto_1fr_auto] gap-4">
              <PanelShell title="Live options tape">
                <div className="grid grid-cols-5 border-b border-[var(--df-border)] px-3 py-2 font-mono text-[9px] font-bold uppercase tracking-normal text-[var(--df-text-muted)]">
                  <span>Contract</span>
                  <span className="text-right">Bid</span>
                  <span className="text-right">Ask</span>
                  <span className="text-right">Delta</span>
                  <span className="text-right">Volume</span>
                </div>
                {DESK_ROWS.map((row) => (
                  <div key={row.strike} className="grid grid-cols-5 border-b border-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-[12px] tabular-nums">
                    <span className="font-bold text-[var(--df-text)]">{row.strike}</span>
                    <span className="text-right font-semibold text-[var(--df-down)]">{row.bid}</span>
                    <span className="text-right font-semibold text-[var(--df-up)]">{row.ask}</span>
                    <span className="text-right text-[var(--df-text-dim)]">{row.delta}</span>
                    <span className="text-right text-[var(--df-text-dim)]">{row.vol}</span>
                  </div>
                ))}
              </PanelShell>

              <PanelShell
                title="Volatility surface"
                action={<span className="font-mono text-[10px] text-[var(--df-accent)]">SPY / 7D</span>}
              >
                <div className="grid h-full min-h-[250px] grid-cols-8 grid-rows-6 gap-px p-3">
                  {Array.from({ length: 48 }).map((_, i) => {
                    const hot = i % 7 === 0 || i % 11 === 0
                    const cool = i % 5 === 0
                    return (
                      <div
                        key={i}
                        className="border border-[rgba(255,255,255,0.03)]"
                        style={{
                          background: hot
                            ? "rgba(245,166,35,0.20)"
                            : cool
                              ? "rgba(56,207,224,0.14)"
                              : "rgba(255,255,255,0.035)",
                        }}
                      />
                    )
                  })}
                </div>
              </PanelShell>

              <div className="grid grid-cols-2 gap-4">
                <PanelShell title="Order book">
                  <MiniBook />
                </PanelShell>
                <PanelShell title="Risk posture">
                  <div className="grid gap-2 p-3 font-mono text-[11px] tabular-nums">
                    <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Net delta</span><span className="text-[var(--df-up)]">+0.118</span></div>
                    <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Gamma</span><span className="text-[var(--df-text)]">0.0241</span></div>
                    <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Theta/day</span><span className="text-[var(--df-down)]">-42.18</span></div>
                    <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Hedge</span><span className="text-[var(--df-accent)]">Ready</span></div>
                  </div>
                </PanelShell>
              </div>
            </section>
          </div>
        </div>
      </main>
    )
  }

  const chain = partial?.options_chain ?? []
  const spotPrice = partial?.spot_price ?? 0
  const symbol = partial?.symbol ?? stream.symbol ?? "-"

  const streamHedge = partial?.hedge ?? null
  const hedge: HedgeRecommendation | null =
    streamHedge && railGreeks
      ? {
          ...streamHedge,
          current_portfolio_delta: railGreeks.delta,
          residual_delta_after_hedge: streamHedge.delta_target - railGreeks.delta,
        }
      : streamHedge

  return (
    <ExplainProvider>
      <div className="relative min-h-screen" style={{ background: "var(--df-bg, #0a0b0d)" }}>
        <SiteBg />

        <div className="relative z-10">
          <Header />

          <main className="mx-auto grid max-w-[1720px] grid-cols-1 gap-3 px-3 py-3 sm:px-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
            <aside data-slot="portfolio-rail" className="hidden lg:block">
              <PortfolioRail
                fallbackSymbol={stream.symbol}
                dteMax={stream.dteMax ?? 7}
                onGreeksChange={setRailGreeks}
              />
            </aside>

            <div className="flex min-w-0 flex-col gap-3">
              <div className="terminal-panel flex flex-wrap items-center justify-between gap-3 px-3 py-2">
                <AnalyzeForm
                  onAnalyze={handleAnalyze}
                  isStreaming={isStreaming}
                  error={error}
                  initialSymbol={stream.symbol ?? "SPY"}
                  initialDteMax={stream.dteMax ?? 7}
                  compact
                />
                <div className="hidden items-center gap-1.5 xl:flex">
                  <span className="term-label mr-1">Switch</span>
                  {QUICK_PICKS.slice(0, 5).map((s) => (
                    <button
                      key={s}
                      type="button"
                      disabled={isStreaming}
                      onClick={() => handleAnalyze(s, stream.dteMax ?? 7)}
                      className="rounded-sm px-2.5 py-1.5 font-mono text-[11px] font-bold uppercase transition-colors"
                      style={{
                        background: symbol === s ? "var(--df-accent-soft, rgba(245,166,35,0.12))" : "rgba(255,255,255,0.04)",
                        border: `1px solid ${symbol === s ? "rgba(245,166,35,0.45)" : "rgba(255,255,255,0.08)"}`,
                        color: symbol === s ? "var(--df-accent,#f5a623)" : "var(--df-text-dim,#9aa1ab)",
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <PanelState
                status={hudStatus}
                errorMessage={error}
                emptyTitle="Greeks pending"
                skeleton={
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <HudCardSkeleton key={i} />
                    ))}
                  </div>
                }
              >
                {partial?.portfolio_greeks && (
                  <HUDCards
                    spotPrice={spotPrice}
                    expiry={partial.expiry ?? "-"}
                    ivRank={partial.iv_rank ?? 0}
                    greeks={partial.portfolio_greeks}
                  />
                )}
              </PanelState>

              <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
                <div className="flex min-w-0 flex-col gap-3">
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
                </div>

                <div className="flex min-w-0 flex-col gap-3">
                  <PanelState
                    status={ivStatus}
                    errorMessage={error}
                    emptyTitle="IV surface pending"
                    skeleton={<CardSkeleton height={190} />}
                  >
                    <IVSurfacePlot options={chain} />
                  </PanelState>

                  <PanelState
                    status={hedgeStatus}
                    errorMessage={error}
                    emptyTitle="Hedge pending"
                    skeleton={<CardSkeleton height={260} />}
                  >
                    {hedge && <HedgePanel hedge={hedge} />}
                  </PanelState>
                </div>
              </div>

              <section data-slot="scenario-panel">
                <ScenarioPanel />
              </section>
            </div>

            <aside className="hidden min-w-0 flex-col gap-3 xl:flex">
              <PanelShell
                title="Market depth"
                action={<span className="font-mono text-[10px] text-[var(--df-up)]">LIVE</span>}
              >
                <MiniBook />
              </PanelShell>

              <PanelState
                status={summaryStatus}
                errorMessage={error}
                emptyTitle="Narrative pending"
                skeleton={<CardSkeleton height={120} />}
              >
                {partial?.risk_summary && (
                  <PanelShell title="Risk summary">
                    <p className="px-3 py-3 font-mono text-[11px] leading-relaxed text-[var(--df-text-dim)]">
                      {partial.risk_summary}
                    </p>
                  </PanelShell>
                )}
              </PanelState>

              <PanelShell title="Session">
                <div className="grid gap-2 p-3 font-mono text-[11px] tabular-nums">
                  <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Symbol</span><span className="font-bold text-[var(--df-text)]">{symbol}</span></div>
                  <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Spot</span><span className="font-bold text-[var(--df-text)]">${spotPrice.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">Rows</span><span className="text-[var(--df-text-dim)]">{chain.length}</span></div>
                  <div className="flex justify-between"><span className="text-[var(--df-text-muted)]">DTE max</span><span className="text-[var(--df-accent)]">{stream.dteMax ?? 7}D</span></div>
                </div>
              </PanelShell>

              <div className="mt-auto flex items-center justify-between border-t border-[var(--df-border)] pt-3 font-mono text-[10px] text-[var(--df-text-muted)]">
                <span>{DISCLAIMER}</span>
                <span className="font-bold text-[var(--df-accent)]">DF</span>
              </div>
            </aside>
          </main>
        </div>

        <ExplainDrawer />
      </div>
    </ExplainProvider>
  )
}
