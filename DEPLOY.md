# Deploying DeltaForge — Render (backend) + Vercel (frontend)

Two services: the **FastAPI backend** on Render and the **Next.js frontend** on Vercel,
talking to your existing **Supabase Postgres**.

---

## ⚠️ Read first: Wolfram in the cloud

The headline feature — the **real Wolfram kernel** — runs from a **local Wolfram Engine
install**. A standard Render container does **not** have Wolfram Engine, so in the cloud the
backend runs in **`numeric_fallback`** mode: the math is still correct (numpy/scipy), and it's
**honestly labeled** ("NUMERIC FALLBACK — NOT WOLFRAM" in the badge) — but it is not the kernel.

To get the **real kernel in production** you have two options:
1. **Bundle Wolfram Engine into the Docker image** — pull `wolframresearch/wolframengine`, activate
   the free license non-interactively (Wolfram ID / on-demand entitlement), set `WOLFRAM_KERNEL_PATH`
   to the in-container kernel. Larger image + you must accept Wolfram's license terms in CI.
2. **Keep the kernel on a self-hosted box** (your machine or a VM with Engine installed) and point
   the deployed backend at it.

For a demo, deploying as-is (cloud = labeled numeric fallback, local dev = real kernel) is fine and
honest. The rest of this guide deploys the standard container.

---

## 1. Backend → Render

The backend ships a `backend/Dockerfile`. On Render, create a **Web Service**:

1. **New → Web Service** → connect this GitHub repo.
2. **Root Directory:** `backend`  •  **Runtime:** Docker (it auto-detects `backend/Dockerfile`).
3. **Instance:** Starter is fine to begin.
4. **Environment variables** (Settings → Environment):

   | Key | Value |
   |---|---|
   | `GROQ_API_KEY` | your Groq key |
   | `DATABASE_URL` | your Supabase **Session pooler** URI (port 5432) |
   | `CORS_ALLOW_ORIGINS` | your Vercel URL, e.g. `https://deltaforge.vercel.app` |
   | `MARKET_DATA_PROVIDER` | `yfinance` |
   | `WOLFRAM_POOL_SIZE` | `1` |
   | `LOG_LEVEL` | `INFO` |

   *(Do NOT set `WOLFRAM_KERNEL_PATH` in the cloud unless you bundled the Engine — without it the
   service correctly starts in `numeric_fallback`.)*

5. **Start command** (if not using the Dockerfile CMD):
   `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. **Run migrations once** against Supabase. Either add a Render **Pre-Deploy Command**
   `alembic upgrade head`, or run it locally once (already done in dev). The schema is idempotent.
7. Deploy → note the service URL, e.g. `https://deltaforge-api.onrender.com`.

> Supabase note: use the **Session pooler** host (`...pooler.supabase.com:5432`) — it's IPv4, which
> Render reaches; the direct `db.<ref>.supabase.co` host is IPv6-only.

### Optional: `render.yaml` blueprint
Commit this at repo root to make Render one-click (fill envs in the dashboard, not here):
```yaml
services:
  - type: web
    name: deltaforge-api
    runtime: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    preDeployCommand: alembic upgrade head
    envVars:
      - key: GROQ_API_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: CORS_ALLOW_ORIGINS
        sync: false
      - key: MARKET_DATA_PROVIDER
        value: yfinance
      - key: WOLFRAM_POOL_SIZE
        value: "1"
```

---

## 2. Frontend → Vercel

1. **vercel.com → Add New → Project** → import this repo.
2. **Root Directory:** `frontend` (click *Edit* and select it).
3. Framework preset: **Next.js** (auto-detected). Build/install commands: defaults.
4. **Environment variable:**

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | your Render backend URL, e.g. `https://deltaforge-api.onrender.com` |

5. **Deploy.** Vercel gives you `https://<project>.vercel.app`.
6. **Close the loop:** put that Vercel URL into the backend's `CORS_ALLOW_ORIGINS` on Render and
   redeploy the backend (so the browser isn't blocked by CORS).

### Or via CLI
```bash
cd frontend
npx vercel            # preview
npx vercel --prod     # production
# set the env var:
npx vercel env add NEXT_PUBLIC_API_URL production
```

---

## 3. Post-deploy smoke check
- `GET https://<render-url>/health` → `{"status":"ok"}`
- `GET https://<render-url>/health/wolfram` → `engine_in_use` will be `numeric_fallback` in the cloud
  (expected, unless you bundled the Engine).
- Open the Vercel URL → pick a ticker → **Run Analysis** → the chain, Greeks, hedge, and scenario fill.

## 4. Secrets hygiene
- `.env` is git-ignored; only `.env.example` is committed. Set real values in the Render/Vercel
  dashboards, never in the repo.
- Rotate any key that was ever pasted into a chat or shared.
