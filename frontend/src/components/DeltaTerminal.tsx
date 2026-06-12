"use client"

import { useEffect, useRef, useState } from "react"

/**
 * DeltaTerminal — a streaming, blinking "live pipeline" log (ported from the
 * siren hero terminal). Lines appear sequentially with staggered delays (the
 * "moving" text), a cursor blinks at the tail (the "blinking" text), and the
 * whole sequence loops. Fully theme-aware via the --df-* tokens so it works in
 * both light and dark modes.
 */

interface Line {
  delay: number
  text: string
  color: string
}

const LINES: Line[] = [
  { delay: 0, text: "Connecting to Wolfram Engine kernel…", color: "var(--df-text-muted)" },
  { delay: 650, text: "fetch_options_chain SPY  dte<=7  →  353 contracts", color: "var(--df-cyan)" },
  { delay: 1450, text: "greeks: D[BlackScholes, S] across the chain…", color: "var(--df-cyan)" },
  { delay: 2250, text: "spot=737.76   iv_rank=5.1%   pin_risk=0.00", color: "var(--df-text)" },
  { delay: 3050, text: "NMinimize  delta-neutral hedge  →  2× 738C", color: "var(--df-accent)" },
  { delay: 3850, text: "kernel verified: 62/62 computations   engine=wolfram", color: "var(--df-up)" },
  { delay: 4650, text: "expected 1d P&L:  −$245.50 … +$892.30", color: "var(--df-up)" },
  { delay: 5450, text: "Symbolic math doesn't hallucinate. It computes.", color: "var(--df-text)" },
]

export function DeltaTerminal() {
  const [visible, setVisible] = useState<number[]>([])
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    function play() {
      setVisible([])
      timers.current.forEach(clearTimeout)
      timers.current = []
      LINES.forEach((line, i) => {
        timers.current.push(setTimeout(() => setVisible((v) => [...v, i]), line.delay))
      })
      const lastDelay = LINES[LINES.length - 1].delay
      timers.current.push(setTimeout(play, lastDelay + 6000))
    }
    play()
    return () => timers.current.forEach(clearTimeout)
  }, [])

  return (
    <div
      className="cb-card w-full"
      style={{
        padding: "16px 18px",
        fontFamily: "var(--font-mono), ui-monospace, monospace",
        fontSize: 12,
        lineHeight: "20px",
        minHeight: 224,
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span
          className="w-1.5 h-1.5 rounded-full inline-block"
          style={{ background: "var(--df-up)", animation: "blink 1.4s step-end infinite" }}
        />
        <span className="term-label">live pipeline</span>
        <span className="term-label ml-auto" style={{ color: "var(--df-accent)" }}>
          wolfram · streaming
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {LINES.map((line, i) =>
          visible.includes(i) ? (
            <div key={i} className="flex gap-2 items-start" style={{ animation: "term-fade-in 0.35s ease" }}>
              <span style={{ color: "var(--df-accent)", flexShrink: 0 }}>&gt;</span>
              <span style={{ color: line.color }}>{line.text}</span>
            </div>
          ) : null,
        )}
        {visible.length > 0 && (
          <div className="flex gap-2 items-center">
            <span style={{ color: "var(--df-accent)" }}>&gt;</span>
            <span style={{ color: "var(--df-accent)", animation: "blink 1s step-end infinite" }}>_</span>
          </div>
        )}
      </div>
    </div>
  )
}
