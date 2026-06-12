"use client"

import { useEffect, useMemo, useRef, useState } from "react"

/** A curated universe of liquid, options-active symbols for fast picking. Free
 *  text is always allowed (the backend accepts any yfinance symbol), so this is
 *  a combobox, not a restricted select. */
export interface TickerOption {
  symbol: string
  name: string
  kind: "ETF" | "Stock" | "Index"
}

export const POPULAR_TICKERS: TickerOption[] = [
  { symbol: "SPY", name: "SPDR S&P 500 ETF", kind: "ETF" },
  { symbol: "QQQ", name: "Invesco QQQ (Nasdaq 100)", kind: "ETF" },
  { symbol: "IWM", name: "iShares Russell 2000", kind: "ETF" },
  { symbol: "DIA", name: "SPDR Dow Jones", kind: "ETF" },
  { symbol: "NVDA", name: "NVIDIA Corp.", kind: "Stock" },
  { symbol: "AAPL", name: "Apple Inc.", kind: "Stock" },
  { symbol: "MSFT", name: "Microsoft Corp.", kind: "Stock" },
  { symbol: "AMZN", name: "Amazon.com Inc.", kind: "Stock" },
  { symbol: "TSLA", name: "Tesla Inc.", kind: "Stock" },
  { symbol: "META", name: "Meta Platforms", kind: "Stock" },
  { symbol: "GOOGL", name: "Alphabet Inc.", kind: "Stock" },
  { symbol: "AMD", name: "Advanced Micro Devices", kind: "Stock" },
  { symbol: "NFLX", name: "Netflix Inc.", kind: "Stock" },
  { symbol: "AVGO", name: "Broadcom Inc.", kind: "Stock" },
  { symbol: "JPM", name: "JPMorgan Chase", kind: "Stock" },
  { symbol: "COIN", name: "Coinbase Global", kind: "Stock" },
]

const KIND_COLOR: Record<TickerOption["kind"], string> = {
  ETF: "#f5a623",
  Stock: "#2bd4a0",
  Index: "#f4b000",
}

interface Props {
  value: string
  onChange: (symbol: string) => void
  /** Fired when a row is committed via Enter/click (lets the parent auto-run). */
  onCommit?: (symbol: string) => void
  disabled?: boolean
}

export default function TickerCombobox({ value, onChange, onCommit, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q) return POPULAR_TICKERS
    return POPULAR_TICKERS.filter(
      (t) => t.symbol.includes(q) || t.name.toUpperCase().includes(q),
    )
  }, [query])

  const typed = query.trim().toUpperCase()
  const showFreeEntry =
    typed.length > 0 && !filtered.some((t) => t.symbol === typed)

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", onDocClick)
    return () => document.removeEventListener("mousedown", onDocClick)
  }, [])

  function commit(symbol: string) {
    const s = symbol.trim().toUpperCase()
    if (!s) return
    onChange(s)
    setQuery("")
    setOpen(false)
    onCommit?.(s)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const total = filtered.length + (showFreeEntry ? 1 : 0)
    if (e.key === "ArrowDown") {
      e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, total - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      if (showFreeEntry && active === filtered.length) commit(typed)
      else if (filtered[active]) commit(filtered[active].symbol)
      else if (typed) commit(typed)
    } else if (e.key === "Escape") {
      setOpen(false)
    }
  }

  return (
    <div ref={rootRef} className="relative" style={{ width: 268 }}>
      {/* Trigger / search field */}
      <div
        className="flex items-center gap-2.5 transition-all"
        style={{
          background: "rgba(255,255,255,0.05)",
          border: `1px solid ${open ? "rgba(245,166,35,0.55)" : "var(--df-border-strong, rgba(255,255,255,0.10))"}`,
          borderRadius: 12,
          height: 44,
          padding: "0 12px 0 14px",
          boxShadow: open ? "0 0 0 3px rgba(245,166,35,0.12)" : "none",
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ flexShrink: 0, opacity: 0.55 }}>
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" style={{ color: "var(--df-text-dim,#a8acb3)" }} />
          <path d="m20 20-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ color: "var(--df-text-dim,#a8acb3)" }} />
        </svg>
        <input
          ref={inputRef}
          type="text"
          value={open ? query : value}
          placeholder={open ? "Search ticker…" : value}
          disabled={disabled}
          onFocus={() => { setOpen(true); setQuery("") }}
          onChange={(e) => { setQuery(e.target.value.toUpperCase()); setActive(0); setOpen(true) }}
          onKeyDown={onKeyDown}
          spellCheck={false}
          autoComplete="off"
          className="flex-1 bg-transparent font-mono text-sm font-bold uppercase focus:outline-none"
          style={{ color: "var(--df-text,#fff)", letterSpacing: "0.06em", minWidth: 0 }}
        />
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"
          style={{ flexShrink: 0, opacity: 0.5, transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }}>
          <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--df-text-dim,#a8acb3)" }} />
        </svg>
      </div>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute left-0 right-0 z-50 mt-2 overflow-hidden"
          style={{
            background: "rgba(14,16,20,0.96)",
            border: "1px solid rgba(255,255,255,0.10)",
            borderRadius: 14,
            backdropFilter: "blur(20px)",
            boxShadow: "0 18px 50px rgba(0,0,0,0.55)",
          }}
        >
          <div className="px-3.5 pt-2.5 pb-1.5 text-[9px] font-bold uppercase tracking-widest" style={{ color: "var(--df-text-muted,#7c828a)" }}>
            {query ? "Matches" : "Popular"}
          </div>
          <div className="max-h-72 overflow-y-auto pb-1.5" role="listbox">
            {filtered.map((t, i) => (
              <Row
                key={t.symbol}
                t={t}
                activeRow={i === active}
                onPick={() => commit(t.symbol)}
                onHover={() => setActive(i)}
              />
            ))}
            {showFreeEntry && (
              <button
                type="button"
                onMouseEnter={() => setActive(filtered.length)}
                onClick={() => commit(typed)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 text-left transition-colors"
                style={{ background: active === filtered.length ? "rgba(245,166,35,0.14)" : "transparent" }}
              >
                <span className="font-mono text-sm font-bold" style={{ color: "var(--df-accent,#f5a623)" }}>{typed}</span>
                <span className="text-xs" style={{ color: "var(--df-text-muted,#7c828a)" }}>— analyze custom ticker</span>
              </button>
            )}
            {filtered.length === 0 && !showFreeEntry && (
              <div className="px-3.5 py-4 text-center text-xs" style={{ color: "var(--df-text-muted,#7c828a)" }}>
                Type a ticker symbol…
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ t, activeRow, onPick, onHover }: {
  t: TickerOption; activeRow: boolean; onPick: () => void; onHover: () => void
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={activeRow}
      onMouseEnter={onHover}
      onClick={onPick}
      className="w-full flex items-center gap-3 px-3.5 py-2 text-left transition-colors"
      style={{ background: activeRow ? "rgba(255,255,255,0.06)" : "transparent" }}
    >
      <span className="font-mono text-sm font-bold w-14 flex-shrink-0" style={{ color: "var(--df-text,#fff)", letterSpacing: "0.04em" }}>
        {t.symbol}
      </span>
      <span className="flex-1 text-xs truncate" style={{ color: "var(--df-text-dim,#a8acb3)" }}>{t.name}</span>
      <span
        className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-md flex-shrink-0"
        style={{ color: KIND_COLOR[t.kind], background: `${KIND_COLOR[t.kind]}1f` }}
      >
        {t.kind}
      </span>
    </button>
  )
}
