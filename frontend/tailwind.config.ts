import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        // Coinbase design tokens
        cb: {
          blue: "#0052ff",
          "blue-active": "#003ecc",
          "blue-disabled": "#a8b8cc",
          ink: "#0a0b0d",
          body: "#5b616e",
          muted: "#7c828a",
          "muted-soft": "#a8acb3",
          hairline: "#dee1e6",
          "hairline-soft": "#eef0f3",
          canvas: "#ffffff",
          "surface-soft": "#f7f7f7",
          "surface-strong": "#eef0f3",
          dark: "#0a0b0d",
          "dark-elevated": "#16181c",
          "on-dark": "#ffffff",
          "on-dark-soft": "#a8acb3",
          up: "#05b169",
          down: "#cf202f",
          yellow: "#f4b000",
        },
      },
      fontFamily: {
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "24px",
        "2xl": "32px",
        pill: "100px",
      },
    },
  },
  plugins: [],
};

export default config;
