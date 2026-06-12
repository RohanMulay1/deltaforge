"use client"

import type { PortfolioGreeks } from "@/types"

interface HUDCardsProps {
  spotPrice: number
  expiry: string
  ivRank: number
  greeks: Pick<PortfolioGreeks, "delta" | "gamma" | "theta">
}

interface CardProps {
  label: string
  value: string
  sub?: string
  valueColor?: string
  accent?: string
}

function HUDCard({ label, value, sub, valueColor, accent }: CardProps) {
  return (
    <div
      className="cb-card cb-hud-card px-3 py-3 cursor-default"
      style={accent ? { borderTop: `2px solid ${accent}` } : undefined}
    >
      <p
        className="text-[10px] font-semibold uppercase tracking-widest mb-2"
        style={{ color: "var(--df-text-muted, #7c828a)", letterSpacing: "0.12em" }}
      >
        {label}
      </p>
      <p
        className="font-mono text-xl font-medium tabular-nums number-in"
        style={{ color: valueColor ?? "var(--df-text, #ffffff)", lineHeight: 1 }}
      >
        {value}
      </p>
      {sub && (
        <p className="font-mono text-[10px] uppercase tracking-wide mt-1.5" style={{ color: "var(--df-text-muted, #7c828a)" }}>
          {sub}
        </p>
      )}
    </div>
  )
}

export function HUDCards({ spotPrice, expiry, ivRank, greeks }: HUDCardsProps) {
  const { delta, gamma, theta } = greeks
  const deltaColor = delta >= 0 ? "var(--df-up, #05b169)" : "var(--df-down, #cf202f)"
  const deltaPrefix = delta >= 0 ? "+" : ""

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      <HUDCard
        label="Spot Price"
        value={`$${spotPrice.toFixed(2)}`}
        sub={`ATM  ${expiry}`}
        valueColor="var(--df-text, #ffffff)"
        accent="var(--df-accent, #f5a623)"
      />
      <HUDCard
        label="IV Rank"
        value={`${ivRank.toFixed(1)}%`}
        valueColor="var(--df-warn, #f4b000)"
        accent="var(--df-warn, #f4b000)"
      />
      <HUDCard
        label="Delta"
        value={`${deltaPrefix}${delta.toFixed(3)}`}
        valueColor={deltaColor}
        accent={deltaColor}
      />
      <HUDCard
        label="Gamma"
        value={`${gamma >= 0 ? "+" : ""}${gamma.toFixed(4)}`}
        valueColor="var(--df-text, #ffffff)"
      />
      <HUDCard
        label="Theta"
        value={theta.toFixed(3)}
        valueColor="var(--df-down, #cf202f)"
        accent="var(--df-down, #cf202f)"
      />
    </div>
  )
}
