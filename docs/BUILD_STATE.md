# DeltaForge — Build State / Resume Handoff

> Read this + `docs/ARCHITECTURE.md` + `docs/BUILD_PLAN.md`. This file is the live status.

## ✅ BUILD COMPLETE (all of P0–P4 + live e2e verified)
Production rebuild of an options hedging terminal. **Wolfram is the headline and it is REAL** (local Wolfram Engine 14.3, free dev license). End-to-end verified live:
- Backend boots; `/health/wolfram` → `engine_in_use: wolfram` (kernel live, canary verified).
- `POST /analyze SPY` → HTTP 200, full populated `AnalyzeResponse`, **62/62 Wolfram computations on the real kernel, ZERO fallbacks** (chain Greeks + NMinimize hedge + scenario surface). spot $737.76, 353 chain rows, e.g. strike 723 delta 0.7776/gamma 0.01489.
- Live Supabase migration applied (8 tables, `alembic current=0001`).
- Frontend renders the full styled dashboard (Portfolio rail + HUD + chain + IV surface + hedge + Scenario P&L + Explain drawer); `next build` + `tsc` clean. Screenshot: `df_dashboard.png`.

### Bugs fixed during e2e (all resolved):
1. `cachetools` missing from requirements.txt → added.
2. Chain Greeks all fell back: ROOT CAUSE was 0-DTE (same-day) expiry → time-to-expiry T≈0 → BS `d1` divides by zero → `Power::infy`/`Indeterminate` on every contract. FIX: `years_to_expiry` floors at `_MIN_TTE_DAYS=1.0` day (`graph/nodes/builders.py`). Also added a benign-message `Quiet[...]` guard in `session_pool.py`. Result: 62/62 now `wolfram`.

### To run locally:
- Backend: `cd backend && WOLFRAM_KERNEL_PATH="C:\Program Files\Wolfram Research\Wolfram Engine\14.3\WolframKernel.exe" ..\.venv\Scripts\python -m uvicorn main:app --port 8000` (`.venv` has full deps installed).
- Frontend: `cd frontend && npm run dev` (port 3000; `NEXT_PUBLIC_API_URL=http://localhost:8000`). On Windows, `npm run dev` child node procs survive TaskStop — kill by port if zombies squat 3000.
- Throwaway smoke/report scripts (`_smoke_*.py`, `_e2e_report.py`, `frontend/_shot.js`, `analyze_spy.json`) can be deleted.

---
## (historical) TL;DR
WS0 + Wave 1 done and verified. Remaining WS2/WS4/WS6/WS7 + migration + e2e — all since COMPLETED (see top).

## Environment — ALL SET (verified)
- `GROQ_API_KEY` — set in `.env`.
- **Wolfram**: local Engine 14.3 at `C:\Program Files\Wolfram Research\Wolfram Engine\14.3\WolframKernel.exe`. `WOLFRAM_KERNEL_PATH` set in `.env`. Kernel VERIFIED live: `wolframscript -code "1+1"` → `2`, and the WolframService pool started a real kernel (engine=WOLFRAM, canary verified, ~109ms eval). **No cloud, no SAK** (free Cloud tier blocks `GenerateSecuredAuthenticationKey[]`).
- **DB**: Supabase Postgres (Session pooler, port 5432). The full `DATABASE_URL` (with the DB password) lives ONLY in the git-ignored `.env` — never commit it. If SQLAlchemy URL parsing chokes on special chars in the password, URL-encode them (e.g. `!` → `%21`).
- Supabase MCP was added then **removed** at user's request — do NOT re-add. App uses the raw Postgres URI only.
- Engine enum is `wolfram` | `numeric_fallback` (renamed from `wolfram_cloud`).

## DONE & VERIFIED (WS0 + Wave 1)
- **WS0**: `backend/models/schemas_*.py` (canonical Pydantic contract), `backend/errors.py`, `backend/services/wolfram/*` (service, session_pool→LOCAL kernel, expressions, fallback, cache, dto), `backend/core/wolfram_settings.py`.
- **WS1**: `backend/providers/*` (MarketDataProvider Protocol + YFinanceProvider off-loop via executor + CachingProvider + retry + factory), `backend/analytics.py` (OFI/pin-risk), `backend/domain/*` (portfolio, greeks_aggregation, hedging), `backend/domain/ingestion/*` (ticket, csv_parser, aliases).
- **WS3**: `backend/db/*` (SQLAlchemy 2.0 async models, repositories, base), `backend/alembic/*` (env.py + `versions/0001_initial_schema.py`, 8 tables, `engine_mode IN ('wolfram','numeric_fallback')`, every table has nullable `user_id`), `backend/core/*` (settings, cors, ratelimit, logging), `backend/routers/{portfolios,watchlist,history}.py`.
- **WS5 (frontend data layer)**: `frontend/src/lib/api/{client,sse,schemas}.ts` (Zod snake_case = single source of truth), `lib/query/queryClient.ts`, `hooks/{useAnalysisStream,usePanelStatus,useWolframHealth}.ts`, `components/feedback/*`, `components/status/SymbolicEngineBadge.tsx`, `components/chain/useChainRows.ts`, `__fixtures__/analysis.fixture.ts`. MOCK_DATA removed from runtime; `page.tsx` shell is stream-driven with empty WS6 slots. `package.json` got `@tanstack/react-query`, `@tanstack/react-virtual`, `zod` (NOT yet npm-installed).
- **Integration**: `backend/main.py` rewritten (thin factory: lifespan wires settings/logging/executor/WolframService/provider/DB; CORS from env; slowapi; exception handlers→ErrorEnvelope; mounts `/health`, `/health/wolfram`, portfolios/watchlist/history; placeholder for analyze/scenario/alerts). `requirements.txt` reconciled. `.env.example` updated. Legacy `agents/wolfram_risk_agent.py` deleted (ported).
- **Verification**: `python -m compileall backend` PASS. Contract review CONFORMS. Live Wolfram smoke test: REAL kernel ran (engine=WOLFRAM).

## OPEN BUGS (Greeks parse to 0.0)
**Bug 1 — FIXED this session, MUST RE-VERIFY.** `build_contract_greeks_expr` in `backend/services/wolfram/expressions.py` emitted `N[<|...|>] /. {S->..}` — `/.` ran AFTER `N[]`, so the kernel returned an unevaluated symbolic association → parser defaulted every Greek to 0. Fix applied: substitution moved INSIDE `N[]` → `N[(<|...|>) /. {S->..}]`. Proven correct: ATM call delta≈0.52, gamma≈0.0216, price≈7.75. **TODO: re-run live smoke test through WolframService (not raw kernel) to confirm delta≈0.52.**

**Bug 2 — NOT yet fixed.** `build_portfolio_greeks_expr` (same file) is broken differently: `bsGreeks[q_, S_, K_, ...]` is applied to numeric rows via `@@@ book`, so S,K,… are bound to NUMBERS, then `D[bs, S]` tries to differentiate w.r.t. a number (725.) → invalid/0. Price term is fine; all derivative Greeks (delta/gamma/vega/theta/rho) are wrong. **Fix needed (next session):** make `bsGreeks` compute symbolic `D[]` with S,K,… kept symbolic, THEN substitute the row's numerics (mirror the contract_greeks pattern), e.g. build the association symbolically and apply `/. {S->row[[2]], ...}` inside `N[]` per leg. Verify portfolio delta = Σ signed_qty×mult×leg_delta is sane. Also confirm `service.py` `_as_float()`/`_greeks_from_result()` coerce the numeric result dict correctly.

## DONE since (wave wvkpitthe — backend complete)
- **Greeks FIXED + verified through real kernel**: contract delta=0.5217/gamma=0.0216/price=7.749; portfolio aggregate delta=160.84; engine=wolfram. `WL_BUILDER_VERSION`=1.1.0. `service.py` parsing already correct (unchanged).
- **WS2**: `graph/pipeline.py` + `state.py` rewritten (market_data→greeks→portfolio→hedge→scenario→summary); `routers/{analyze,scenario,trade_ticket}.py`; `sse.py`. Entrypoints `run_analysis(req)->AnalyzeResponse` and `analysis_event_stream(req)`.
- **WS4**: `ops/{scheduler,alert_evaluator}.py`, `routers/alerts.py`.
- **Integrated**: main.py mounts analyze/scenario/trade_ticket/alerts + starts APScheduler.
- **LIVE Supabase migration DONE**: `alembic upgrade head` → `0001 (head)`, 8 tables created. `!!` password parsed fine (no encoding needed). Venv at `.venv` has migration deps only; full boot needs `pip install -r backend/requirements.txt`.
- WolframService signatures captured (see wave report): `contract_greeks(GreekInputs)`, `portfolio_greeks(Sequence[Position])`, `delta_neutral_hedge(HedgeRequest)`, `pnl_surface(PnLSurfaceInputs)`, `health()`; lifecycle `start()/stop()`. Theta is per-YEAR at service layer (÷365 at UI).
- NOTE: `DATABASE_URL` only in repo-root `.env`; settings loader must read root `.env` (env.py needs the var in process env). E2E phase fixes this if needed.

## REMAINING (wave w62up65gl RUNNING — may be interrupted)
- **WS6** — frontend `components/portfolio/*`, `components/scenario/*`, `components/explain/*` (Explainable + ExplainDrawer = the Wolfram verifiability UI), `lib/portfolio/parseCsv.ts`, `hooks/{usePortfolio,usePortfolioGreeks,useScenarioPnl}.ts`; fill WS6 slots in `page.tsx`; wrap Wolfram values in `<Explainable>`. Add `zustand` to package.json.
- **WS7** — `backend/Dockerfile`, `docker-compose.yml`, `fly.toml`, `backend/tests/*` (fixtures incl. `fake_wolfram`→numeric_fallback) to 80% (`--cov-fail-under=80`, all externals mocked).
- **Final e2e** — `pip install -r backend/requirements.txt` in `.venv`; fix root-`.env` loading; boot uvicorn (port 8000) + `npm install`+`npm run dev` (port 3000); live SPY `/analyze` through kernel; screenshot → `e2e_dashboard.png`; frontend `tsc --noEmit` + `next build`.
- If wave w62up65gl interrupted: resume via `Workflow({scriptPath: ".../deltaforge-impl-final-wf_2d1f4668-6b9.js", resumeFromRunId: "wf_2d1f4668-6b9"})`.

## How to run / deps
- Backend deps NOT installed in a project venv yet. A throwaway `.venv_smoke` may exist (wolframclient numpy scipy mpmath pydantic pydantic-settings) — fine to reuse/remove. For full run: `python -m venv .venv && .venv\Scripts\python -m pip install -r backend/requirements.txt`. Run backend from `backend/` dir (imports are top-level `from models...`, `from services...`).
- Frontend: `cd frontend && npm install && npm run dev` (Next 14, port 3000). `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- Wolfram note: wolframclient prints a benign `Socket exception / Failed to start` on first kernel spawn, then recovers to live — not a real failure.

## Orchestration notes
- Build done via background `Workflow` runs in waves (disjoint file ownership; `main.py`+`requirements.txt` owned only by an integrator step to avoid collisions). Last completed run: `wf_669c652a-082` (task `wfzuupt66`). Scripts saved under `.../workflows/scripts/`.
- **Session limits** killed an earlier run mid-way — keep waves scoped; resume via `resumeFromRunId`.
- Memory: `~/.claude/projects/C--Users-rohan-deltaforge/memory/deltaforge-build.md`.
