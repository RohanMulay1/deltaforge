"use client"

import { useState } from "react"
import TickerCombobox from "@/components/TickerCombobox"

const DTE_OPTIONS = [
  { label: "1D", value: 1 },
  { label: "3D", value: 3 },
  { label: "1W", value: 7 },
  { label: "2W", value: 14 },
  { label: "1M", value: 30 },
]

interface Props {
  /** Kicks off a streamed analysis (parent owns `useAnalysisStream`). */
  onAnalyze: (symbol: string, dteMax: number) => void
  /** True while the SSE stream is open. */
  isStreaming?: boolean
  /** Stream-level error surfaced by the parent hook. */
  error?: string | null
  initialSymbol?: string
  initialDteMax?: number
  /** Hide the pipeline caption (used in the compact dashboard toolbar). */
  compact?: boolean
}

export default function AnalyzeForm({
  onAnalyze,
  isStreaming = false,
  error = null,
  initialSymbol = "SPY",
  initialDteMax = 7,
  compact = false,
}: Props) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [dteMax, setDteMax] = useState(initialDteMax)

  function run(sym: string, dte: number) {
    const trimmed = sym.trim().toUpperCase()
    if (!trimmed) return
    onAnalyze(trimmed, dte)
  }

  return (
    <div>
      <form
        onSubmit={(e) => { e.preventDefault(); run(symbol, dteMax) }}
        className="flex flex-row items-center gap-3 flex-wrap"
      >
        <TickerCombobox value={symbol} onChange={setSymbol} disabled={isStreaming} />

        {/* DTE segmented control */}
        <div className="flex flex-col gap-1">
          {!compact && (
            <span className="text-[9px] font-bold uppercase tracking-widest pl-1" style={{ color: "var(--df-text-muted,#7c828a)" }}>
              Expiry window
            </span>
          )}
          <div
            className="flex flex-row items-center gap-0.5 p-1"
            style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6 }}
          >
            {DTE_OPTIONS.map((opt) => {
              const on = dteMax === opt.value
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setDteMax(opt.value)}
                  className="font-mono text-xs font-semibold transition-all"
                  style={{
                    borderRadius: 4,
                    padding: "7px 13px",
                    height: 34,
                    background: on ? "var(--df-accent, #f5a623)" : "transparent",
                    color: on ? "#0a0a0a" : "var(--df-text-dim, #a8acb3)",
                    border: "none",
                    cursor: "pointer",
                    boxShadow: "none",
                  }}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Run button */}
        <button
          type="submit"
          disabled={isStreaming}
          className="cb-btn-primary flex items-center gap-2"
          style={{ height: 44, alignSelf: compact ? "center" : "flex-end" }}
        >
          {isStreaming ? (
            <>
              <svg className="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              ANALYZING
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M5 3l14 9-14 9V3z" fill="currentColor" />
              </svg>
              RUN ANALYSIS
            </>
          )}
        </button>
      </form>

      {error && (
        <p className="text-xs font-mono mt-2.5" style={{ color: "var(--df-down, #cf202f)" }}>{error}</p>
      )}

      {!compact && (
        <p className="text-xs font-mono mt-3 flex items-center gap-2" style={{ color: "var(--df-text-muted, #7c828a)", letterSpacing: "0.02em" }}>
          <span>Options chain</span><span style={{ color: "var(--df-accent,#f5a623)" }}>→</span>
          <span>Wolfram Greeks</span><span style={{ color: "var(--df-accent,#f5a623)" }}>→</span>
          <span>NMinimize hedge</span>
        </p>
      )}
    </div>
  )
}
