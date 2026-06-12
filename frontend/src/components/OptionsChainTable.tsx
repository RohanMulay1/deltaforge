"use client"

/**
 * OptionsChainTable — virtualized, ATM-anchored options chain (ARCHITECTURE.md
 * §10.3). Uses `@tanstack/react-virtual` so 200+ rows stay smooth; scrolls to
 * the ATM row on load and draws a sticky-ish ATM highlight. A per-row delta
 * column is rendered; WS6 will wrap that delta cell in `<Explainable>`.
 */

import { useEffect, useRef } from "react"

import { useVirtualizer } from "@tanstack/react-virtual"

import { useChainRows, type ChainRow } from "@/components/chain/useChainRows"
import { Explainable } from "@/components/explain/Explainable"
import type { OptionQuote } from "@/types"

interface OptionsChainTableProps {
  rows: OptionQuote[]
  spotPrice: number
  symbol?: string
}

const ROW_HEIGHT = 38
const VIEWPORT_HEIGHT = 460
const ATM_TOLERANCE = 2.5

function getOfiBackground(ofi: number): string {
  if (ofi > 0.5) return "rgba(5,177,105,0.22)"
  if (ofi > 0.2) return "rgba(5,177,105,0.12)"
  if (ofi > 0) return "rgba(5,177,105,0.06)"
  if (ofi < -0.5) return "rgba(207,32,47,0.22)"
  if (ofi < -0.2) return "rgba(207,32,47,0.12)"
  if (ofi < 0) return "rgba(207,32,47,0.06)"
  return "transparent"
}

const COLUMNS = ["STRIKE", "TYPE", "DELTA", "IV", "BID", "ASK", "VOL", "OI", "OFI"] as const

const GRID_TEMPLATE = "1.25fr 0.7fr 0.85fr 0.62fr 0.68fr 0.68fr 1.1fr 1.1fr 0.78fr"

function MetricBar({ value, max, fill }: { value: number; max: number; fill: string }) {
  const ratio = max > 0 ? Math.min(value / max, 1) : 0
  const compact = value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k` : value.toLocaleString()
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="font-mono text-xs tabular-nums shrink-0" style={{ color: "var(--df-text-dim, #a8acb3)", width: 34 }}>
        {compact}
      </span>
      <div className="shrink-0 rounded-full overflow-hidden" style={{ width: 40, height: 4, background: "rgba(255,255,255,0.07)" }}>
        <div className="h-full rounded-full" style={{ width: `${ratio * 40}px`, background: fill }} />
      </div>
    </div>
  )
}

function ChainCells({ row, maxVol, maxOI, isPin }: { row: ChainRow; maxVol: number; maxOI: number; isPin: boolean }) {
  const isCall = row.type === "call"
  const ofiColor = row.ofi >= 0 ? "var(--df-up, #05b169)" : "var(--df-down, #cf202f)"
  const deltaColor = row.delta >= 0 ? "var(--df-up, #05b169)" : "var(--df-down, #cf202f)"

  return (
    <>
      <div className="flex items-center gap-1.5 font-mono text-xs">
        <span className="font-semibold tabular-nums" style={{ color: "var(--df-text, #fff)" }}>{row.strike}</span>
        {row.isAtm && (
          <span
            className="font-mono text-[8px] font-bold px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(245,166,35,0.18)", color: "var(--df-accent, #f5a623)", border: "1px solid rgba(245,166,35,0.3)" }}
          >
            ATM
          </span>
        )}
        {isPin && (
          <span
            className="font-mono text-[8px] font-bold px-1.5 py-0.5 rounded-full"
            title="Max open interest — pin / max-pain magnet"
            style={{ background: "rgba(56,207,224,0.16)", color: "var(--df-cyan, #38cfe0)", border: "1px solid rgba(56,207,224,0.3)" }}
          >
            PIN
          </span>
        )}
      </div>

      <div className="flex items-center">
        <span
          className="font-mono text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
          style={
            isCall
              ? { background: "rgba(245,166,35,0.12)", color: "var(--df-accent, #f5a623)", border: "1px solid rgba(245,166,35,0.25)" }
              : { background: "rgba(207,32,47,0.10)", color: "var(--df-down, #cf202f)", border: "1px solid rgba(207,32,47,0.25)" }
          }
        >
          {row.type}
        </span>
      </div>

      {/* DELTA column — kernel-derived; click opens the shared explain drawer. */}
      <div className="flex items-center font-mono text-xs tabular-nums font-medium" style={{ color: deltaColor }}>
        <Explainable
          computation={row.quote.wolfram}
          title={`${row.type.toUpperCase()} ${row.strike} Δ`}
        >
          <span style={{ color: deltaColor }}>
            {row.delta >= 0 ? "+" : ""}
            {row.delta.toFixed(3)}
          </span>
        </Explainable>
      </div>

      <div className="flex items-center font-mono text-xs tabular-nums" style={{ color: "var(--df-text-dim, #a8acb3)" }}>
        {(row.iv * 100).toFixed(1)}%
      </div>

      <div className="flex items-center font-mono text-xs tabular-nums font-medium" style={{ color: "var(--df-down, #cf202f)" }}>
        {row.bid.toFixed(2)}
      </div>

      <div className="flex items-center font-mono text-xs tabular-nums font-medium" style={{ color: "var(--df-up, #05b169)" }}>
        {row.ask.toFixed(2)}
      </div>

      <div className="flex items-center">
        <MetricBar value={row.volume} max={maxVol} fill="rgba(255,255,255,0.20)" />
      </div>

      <div className="flex items-center">
        <MetricBar value={row.openInterest} max={maxOI} fill="rgba(245,166,35,0.45)" />
      </div>

      <div
        className="flex items-center font-mono text-xs tabular-nums font-semibold px-1.5"
        style={{ color: ofiColor, background: getOfiBackground(row.ofi) }}
      >
        {row.ofi >= 0 ? "+" : ""}
        {row.ofi.toFixed(2)}
      </div>
    </>
  )
}

export function OptionsChainTable({ rows, spotPrice, symbol = "–" }: OptionsChainTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const { rows: chainRows, atmIndex, maxVolume, maxOpenInterest, pinStrike } = useChainRows(rows, spotPrice)

  const virtualizer = useVirtualizer({
    count: chainRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  })

  // ATM-anchored: scroll the nearest-to-spot row into the center on load/change.
  useEffect(() => {
    if (atmIndex >= 0) {
      virtualizer.scrollToIndex(atmIndex, { align: "center" })
    }
  }, [atmIndex, chainRows.length, virtualizer])

  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div className="cb-card overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3.5" style={{ borderBottom: "1px solid var(--df-border, rgba(255,255,255,0.06))" }}>
        <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--df-text-dim, #a8acb3)", letterSpacing: "0.12em" }}>
          Options Chain
        </span>
        <span
          className="font-mono text-[10px] font-bold px-2.5 py-0.5 rounded-full"
          style={{ background: "rgba(245,166,35,0.12)", color: "var(--df-accent, #f5a623)", border: "1px solid rgba(245,166,35,0.25)" }}
        >
          {symbol}
        </span>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse inline-block" style={{ background: "var(--df-up, #05b169)" }} />
          <span className="text-[10px] font-mono" style={{ color: "var(--df-up, #05b169)" }}>Live</span>
        </div>
        {pinStrike !== null && (
          <span
            className="ml-auto font-mono text-[10px] font-bold px-2 py-0.5 rounded-md"
            title="Strike with the largest open interest"
            style={{ background: "rgba(56,207,224,0.12)", color: "var(--df-cyan, #38cfe0)", border: "1px solid rgba(56,207,224,0.25)" }}
          >
            MAX-PAIN {pinStrike}
          </span>
        )}
        <span className={`font-mono text-[10px] ${pinStrike !== null ? "" : "ml-auto"}`} style={{ color: "var(--df-text-muted, #7c828a)" }}>
          {chainRows.length} rows
        </span>
      </div>

      {/* Column header */}
      <div
        className="grid items-center px-5 py-2.5 font-mono text-[10px] font-bold tracking-widest"
        style={{
          gridTemplateColumns: GRID_TEMPLATE,
          color: "var(--df-text-muted, #7c828a)",
          letterSpacing: "0.1em",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        {COLUMNS.map((h) => (
          <span key={h}>{h}</span>
        ))}
      </div>

      {/* Virtualized body */}
      <div ref={scrollRef} style={{ height: VIEWPORT_HEIGHT, overflowY: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
          {virtualItems.map((vItem) => {
            const row = chainRows[vItem.index]
            const isAtmAnchor = Math.abs(row.strike - spotPrice) < ATM_TOLERANCE
            return (
              <div
                key={row.key}
                className="grid items-center px-5 transition-colors"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: ROW_HEIGHT,
                  transform: `translateY(${vItem.start}px)`,
                  gridTemplateColumns: GRID_TEMPLATE,
                  borderBottom: "1px solid rgba(255,255,255,0.03)",
                  borderTop: isAtmAnchor && vItem.index === atmIndex ? "1px solid rgba(245,166,35,0.35)" : undefined,
                  background: isAtmAnchor ? "rgba(245,166,35,0.06)" : "transparent",
                }}
              >
                <ChainCells
                  row={row}
                  maxVol={maxVolume}
                  maxOI={maxOpenInterest}
                  isPin={pinStrike !== null && row.strike === pinStrike}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
