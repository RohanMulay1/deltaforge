"use client"

import { useEffect, useState } from "react"

type Theme = "light" | "dark"

function MoonIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"
        fill="currentColor"
      />
    </svg>
  )
}

function SunIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

/** Pill-shaped light/dark theme slider for the top nav. Persists to localStorage;
 *  the no-flash boot script in layout.tsx applies the saved theme before paint. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark")

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "dark"
    setTheme(current)
  }, [])

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark"
    setTheme(next)
    document.documentElement.setAttribute("data-theme", next)
    document.documentElement.style.colorScheme = next
    try {
      localStorage.setItem("df-theme", next)
    } catch {
      /* storage may be unavailable (private mode) — toggle still works for the session */
    }
  }

  const isDark = theme === "dark"

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={!isDark}
      aria-label="Toggle light or dark theme"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="relative inline-flex items-center flex-shrink-0"
      style={{
        width: 50,
        height: 24,
        borderRadius: 999,
        background: "var(--df-surface)",
        border: "1px solid var(--df-border-strong)",
        padding: 2,
        cursor: "pointer",
      }}
    >
      {/* faint track icons */}
      <span className="absolute" style={{ left: 6, color: "var(--df-text-muted)", opacity: isDark ? 0 : 0.6, transition: "opacity 200ms" }}>
        <MoonIcon size={10} />
      </span>
      <span className="absolute" style={{ right: 6, color: "var(--df-text-muted)", opacity: isDark ? 0.6 : 0, transition: "opacity 200ms" }}>
        <SunIcon size={10} />
      </span>
      {/* sliding knob carrying the active icon */}
      <span
        aria-hidden="true"
        className="inline-flex items-center justify-center"
        style={{
          width: 18,
          height: 18,
          borderRadius: 999,
          background: "var(--df-accent)",
          color: "#0a0a0a",
          transform: isDark ? "translateX(0)" : "translateX(26px)",
          transition: "transform 280ms cubic-bezier(0.16, 1, 0.3, 1)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.35)",
        }}
      >
        {isDark ? <MoonIcon size={10} /> : <SunIcon size={10} />}
      </span>
    </button>
  )
}
