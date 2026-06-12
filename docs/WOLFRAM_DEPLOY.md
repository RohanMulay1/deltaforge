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
| A demo with the real kernel, cheapest | **Option A** (bundle free Engine + mathpass), Render ≥1 GB |
| Real kernel, already have an always-on box | **Option B** (host the backend there) |
| Production SaaS with paying users | **Option C** (paid Wolfram Cloud) or a paid Engine entitlement |
| Just ship something now | Deploy as-is → labeled `numeric_fallback` (correct math, honest badge) |

The app is built so **all four are drop-in**: the engine label is always honest, and the numeric
fallback is never mislabeled as Wolfram — so you can start on fallback and switch the kernel on
later without touching the product.
