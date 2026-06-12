# Running the REAL Wolfram kernel in production

By default the deployed backend (Render container) has **no Wolfram Engine**, so it runs in
honest `numeric_fallback`. This guide gets the **real kernel** (`engine_in_use: wolfram`) running
in the cloud. Read the licensing note first — it's the part that actually matters.

---

## ⚖️ Licensing reality (read this)

The **free Wolfram Engine** license is for **development / personal / pre-production** use. It is
**not** licensed for a production commercial SaaS serving external users. So:

- **Demo / portfolio / pre-production** → bundle the free Engine (Option A below). Fine.
- **Real production with users** → you need a **paid** Wolfram license: a Wolfram Engine
  *production* entitlement, or **Wolfram Cloud** with a Secured Authentication Key (Option C).
  Don't ship the free Engine to paying users.

Everything below is technically identical; only the license you activate with differs.

---

## 🆓 Free Render — what actually fits

**The bundled Engine (Option A) does NOT run on Render's free tier.** Hard blockers:
- Free web service = **512 MB RAM / 0.1 CPU**. A single `WolframKernel` wants **~500 MB–1 GB just
  to start** — it will OOM-crash immediately, before your app even loads.
- The `wolframengine` image is **~6 GB**; free build/disk limits choke on it.
- Free services **sleep after 15 min idle** → a cold kernel boot on every wake is brutal.

So on free Render you have two honest, working options:

### Free path 1 — Backend on free Render, `numeric_fallback` (zero kernel)
The FastAPI backend itself **does** fit free Render (keep it to **1 uvicorn worker**; scipy/numpy
are fine at low traffic). Deploy exactly per `DEPLOY.md` and simply **don't** set
`WOLFRAM_KERNEL_PATH`. Result: correct math, the badge honestly reads "NUMERIC FALLBACK — NOT
WOLFRAM." This is the no-cost, no-kernel demo.

### Free path 2 — REAL kernel for free, via a tunnel (recommended)
Keep the **real backend (with the kernel) on your own machine** — where the free Engine is already
activated — and expose it through a **free Cloudflare Tunnel**. Host only the **frontend** for free
(Render Static Site or Vercel) pointed at the tunnel URL. **Zero code changes** — your local backend
already does real Wolfram.

### One command (Windows)
The repo ships a launcher that boots the backend (if not already up), opens the tunnel, and prints
the public URL — verified working (`engine_in_use: wolfram` reachable over the tunnel):
```powershell
powershell -ExecutionPolicy Bypass -File .\run-and-tunnel.ps1
```
It reuses an already-running backend, reports kernel status, prints the `https://….trycloudflare.com`
URL to paste into the frontend, and cleans up on Ctrl+C. The manual equivalent is below.

```bash
# 1. Run the real backend locally (real kernel, as you do now):
cd backend
WOLFRAM_KERNEL_PATH="C:/Program Files/Wolfram Research/Wolfram Engine/14.3/WolframKernel.exe" \
WOLFRAM_POOL_SIZE=1 ../.venv/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 2. Expose it with a free Cloudflare quick-tunnel (no account needed):
#    install once: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8000
#    -> prints a public https URL like https://random-words.trycloudflare.com
```

Then:
- **Frontend (free):** deploy `frontend/` to **Vercel** (or a **Render Static Site**) with
  `NEXT_PUBLIC_API_URL = https://<your-tunnel>.trycloudflare.com`.
- Set the backend's `CORS_ALLOW_ORIGINS` to that frontend URL and restart it.

Now the publicly-hosted app shows **real `wolfram`** whenever your machine + tunnel are up, and you
paid nothing. (For a stable URL instead of a random quick-tunnel one, create a free **named**
Cloudflare tunnel tied to a domain — same idea.) Caveat: it's only live while your machine is on —
fine for a demo, not 24/7 SaaS (for that, see Option C, paid).

> Trade-off vs. "real cloud": Free path 2 means the kernel lives on your box, not in Render. That's
> the only way to get free + real Wolfram, because no free container tier can host the Engine.

---

## Option A — Bundle Wolfram Engine in the Docker image (real kernel, one container)

This is the most direct path: the kernel lives inside the backend container.

### 1. Export your activated license file (`mathpass`)
On the machine where Engine is already activated, find the license file:
- **Windows:** `C:\Users\<you>\AppData\Roaming\Mathematica\Licensing\mathpass`
  (or under the Wolfram Engine install's `Licensing/` dir)
- **Linux/macOS:** `~/.WolframEngine/Licensing/mathpass` or `~/.Mathematica/Licensing/mathpass`

Copy that `mathpass` file into the repo as `deploy/mathpass` (and **git-ignore it** — it's a
credential):
```
echo "deploy/mathpass" >> .gitignore
```
You'll inject it at deploy time as a secret file, not commit it.

### 2. Dockerfile that includes the Engine + your Python backend
Create `backend/Dockerfile.wolfram`:
```dockerfile
# Official Wolfram Engine image already contains the kernel + wolframscript.
FROM wolframresearch/wolframengine:14.3 AS engine

# Engine images run as the `wolframengine` user; add Python + the backend.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY backend/ /app/

# License: the platform mounts the activated mathpass here as a secret file.
# (Path the Engine looks in; adjust if your image version differs.)
ENV WOLFRAM_KERNEL_PATH=/usr/local/Wolfram/WolframEngine/14.3/Executables/WolframKernel
ENV WOLFRAM_POOL_SIZE=1

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

> The exact kernel path/licensing dir can vary by Engine image version. Verify once with:
> `docker run --rm wolframresearch/wolframengine:14.3 bash -lc 'which WolframKernel; wolframscript -code 1+1'`

### 3. Provide the license at runtime
The container needs the `mathpass` at the Engine's licensing path. Two ways:
- **Bake it in** (simplest, less secure): `COPY deploy/mathpass /root/.WolframEngine/Licensing/mathpass`
  *(only if the image runs as that user; check with the verify command above).*
- **Mount as a secret** (preferred): on Render, add a **Secret File** at the licensing path; on
  Fly.io use `fly secrets`/a volume; in k8s a mounted Secret.

### 4. Deploy on Render
- New **Web Service** → **Root `backend`** → **Docker** → set Dockerfile to `Dockerfile.wolfram`.
- **Instance size:** the kernel needs RAM — use **≥ 1 GB** (Starter 512 MB will OOM). A kernel
  process is ~300–700 MB resident; keep `WOLFRAM_POOL_SIZE=1`.
- Same env vars as `DEPLOY.md` (`GROQ_API_KEY`, `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, …) **plus**
  the mounted `mathpass` secret file.
- Image is large (~5–6 GB with the Engine) → first build/deploy is slow. Subsequent deploys cache.

### 5. Verify
`GET https://<render-url>/health/wolfram` → `{"engine_in_use":"wolfram","wolfram_available":true,...}`.
The frontend badge flips to green **WOLFRAM KERNEL · LIVE**.

---

## Option B — Self-hosted kernel, backend calls it (keeps cloud container slim)

Run Wolfram Engine on a box you control (your machine, a VM, a home server) and have the cloud
backend talk to it. Two sub-paths:

- **Same host:** run the whole backend where the Engine is installed (e.g. a small VM with Engine
  activated) instead of Render. Zero code change — it's exactly your local setup, just on a server.
- **Remote kernel:** keep the backend on Render but point `WolframService` at a remote kernel.
  This needs a small code change: add a remote session backend to
  `backend/services/wolfram/session_pool.py` (a thin HTTP/WSTP shim to the kernel host). The
  service is already abstracted for this — the DTOs/fallback don't change, only the session class.

Use this if you don't want a 6 GB image, or you already have an always-on machine with Engine.

---

## Option C — Wolfram Cloud (paid, no container kernel)

If you buy **Wolfram Cloud**, you can use the originally-planned hosted path:
1. In Wolfram Cloud, run `GenerateSecuredAuthenticationKey[]` → get `ConsumerKey` + `ConsumerSecret`.
2. Add a Cloud session backend to `session_pool.py`:
   ```python
   from wolframclient.evaluation import WolframCloudSession
   from wolframclient.evaluation import SecuredAuthenticationKey as SAK
   session = WolframCloudSession(credentials=SAK(key, secret))
   ```
   gated on env `WOLFRAM_BACKEND=cloud` + `WOLFRAM_CONSUMER_KEY`/`_SECRET`.
3. Deploy the slim container (no Engine), set those env vars. The kernel runs in Wolfram's cloud.

Pro: tiny image, no license file to manage, production-licensed. Con: per-call latency + Cloud
credits/cost, requires a paid plan (the free tier blocks SAK generation).

---

## TL;DR decision

| You want… | Do this |
|---|---|
| **Free Render + real Wolfram** | **Free path 2**: local backend + Cloudflare tunnel, free frontend on Vercel/Render-static |
| **Free Render, no kernel** | **Free path 1**: backend on free Render in `numeric_fallback` (1 worker) |
| Real kernel in a real cloud container | **Option A** (bundle Engine + mathpass) — needs a **paid ≥1 GB** instance, NOT free |
| Real kernel, already have an always-on box | **Option B** (host the backend there) |
| Production SaaS with paying users | **Option C** (paid Wolfram Cloud) or a paid Engine entitlement |

**Bottom line for free Render:** you cannot run the Engine *inside* a free Render container — but you
*can* have the publicly-hosted app use the real kernel by tunneling to it on your machine (Free
path 2), or deploy honestly in `numeric_fallback` (Free path 1).

The app is built so **all four are drop-in**: the engine label is always honest, and the numeric
fallback is never mislabeled as Wolfram — so you can start on fallback and switch the kernel on
later without touching the product.
