"use client"

import { useEffect, useState } from "react"

import { SymbolicEngineBadge } from "@/components/status/SymbolicEngineBadge"

function StatusDot({ color }: { color: string }) {
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-50" style={{ background: color }} />
      <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: color }} />
    </span>
  )
}

export function Header() {
  const [time, setTime] = useState<string>("")

  useEffect(() => {
    const fmt = () => {
      const n = new Date()
      return [n.getHours(), n.getMinutes(), n.getSeconds()]
        .map(v => String(v).padStart(2, "0"))
        .join(":")
    }
    setTime(fmt())
    const id = setInterval(() => setTime(fmt()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <header
      className="sticky top-0 z-50 w-full"
      style={{
        height: 52,
        background: "rgba(8,9,12,0.88)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--df-border-strong, rgba(255,255,255,0.11))",
      }}
    >
      <div className="max-w-[1720px] mx-auto h-full flex items-center px-5 gap-4">
        {/* Wordmark (no logo) */}
        <div className="flex items-baseline gap-2">
          <span
            className="font-mono text-[15px] font-bold tracking-tight"
            style={{ color: "var(--df-text,#e9ebee)", letterSpacing: "-0.3px" }}
          >
            DELTA<span style={{ color: "var(--df-accent,#f5a623)" }}>FORGE</span>
          </span>
          <span className="term-label" style={{ color: "var(--df-text-muted,#616773)" }}>
            options risk terminal
          </span>
        </div>

        {/* Live clock (mono, terminal) */}
        <div className="flex-1 flex justify-center">
          <span className="font-mono text-[13px] tabular-nums" style={{ color: "var(--df-text-dim,#9aa1ab)", letterSpacing: "0.12em" }}>
            {time} <span style={{ color: "var(--df-text-muted,#616773)" }}>UTC{new Date().getTimezoneOffset() <= 0 ? "+" : "-"}</span>
          </span>
        </div>

        {/* Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <StatusDot color="var(--df-up, #16c784)" />
            <span className="font-mono text-[10px] font-bold tracking-wide" style={{ color: "var(--df-up, #16c784)" }}>LIVE</span>
          </div>
          <SymbolicEngineBadge />
        </div>
      </div>
    </header>
  )
}
