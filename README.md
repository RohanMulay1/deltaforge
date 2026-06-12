# DeltaForge — Options Risk Terminal

Options risk & **delta-neutral hedging, computed by a real Wolfram Engine kernel** — not an LLM
guess. Every Greek, hedge, and P&L surface ships the exact Wolfram Language expression it ran, so
the math is reproducible. The numeric fallback (when no kernel is reachable) is always labeled
honestly, never passed off as Wolfram.

> Symbolic math doesn't hallucinate. It computes.

## What it does
- **Live options chain** (yfinance, behind a swappable provider interface) with per-strike Greeks,
  OI bars, and a max-pain marker.
- **Symbolic Greeks** via `D[BlackScholes, …]` on a real Wolfram kernel.
- **Multi-leg delta-neutral hedge** via `NMinimize` against your actual portfolio delta.
- **Scenario P&L surface** across spot × IV × time.
- **Streaming pipeline** (SSE) → a Next.js terminal dashboard with light/dark theming, a portfolio
  rail, scenario sliders, and an "explain the math" drawer that shows the exact WL expression + the
  kernel-verified result for any number.

## Repository layout
```
deltaforge/
├── backend/            FastAPI + LangGraph pipeline, WolframService, providers, domain, db, tests
├── frontend/           Next.js 14 app (App Router) — terminal UI, light/dark, SSE dashboard
├── docs/               ARCHITECTURE · BUILD_PLAN · BUILD_STATE · DEPLOY · WOLFRAM_DEPLOY
├── scripts/            run-and-tunnel.ps1  (free-Render real-kernel launcher)
├── docker-compose.yml  local dev (backend + frontend; Postgres is hosted via DATABASE_URL)
├── .env.example        documented env vars (copy to .env and fill in)
└── .gitignore
```

## Quick start (local)
**1. Backend** (needs Python 3.11 + a local Wolfram Engine for the real kernel; falls back to
numeric otherwise):
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
cp .env.example .env          # fill GROQ_API_KEY, DATABASE_URL, WOLFRAM_KERNEL_PATH
cd backend && ../.venv/Scripts/python -m uvicorn main:app --port 8000
```
**2. Frontend:**
```bash
cd frontend && npm install && npm run dev      # http://localhost:3000
```
Set `frontend/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8000`.

**Tests:** `cd backend && pytest`  ·  **Build check:** `cd frontend && npm run build`

## Configuration
All secrets/config come from `.env` (git-ignored) — see `.env.example`. Required: `GROQ_API_KEY`,
`DATABASE_URL` (Supabase/Postgres). Optional: `WOLFRAM_KERNEL_PATH` (omit → labeled numeric
fallback), `WOLFRAM_POOL_SIZE` (1 recommended on the free Engine), `CORS_ALLOW_ORIGINS`.

## Deployment
- **Backend + Frontend:** `docs/DEPLOY.md` (Render + Vercel).
- **Real Wolfram kernel in the cloud (incl. free-Render via tunnel):** `docs/WOLFRAM_DEPLOY.md`.
  One-command launcher for the free-tunnel path: `scripts/run-and-tunnel.ps1`.

## Architecture & status
See `docs/ARCHITECTURE.md` (canonical design + API contract) and `docs/BUILD_STATE.md` (live status).

---
*Informational only. Not investment advice. No live execution.*
