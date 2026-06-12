# DeltaForge backend — multi-stage image (ARCHITECTURE.md §11.1).
#
# Stage 1 (builder): installs build-essential ONLY to compile the few wheels
# that need it (scipy / asyncpg), into an isolated virtualenv.
# Stage 2 (runtime): slim, non-root, copies the prebuilt venv. No compilers.
#
# Wolfram note: `wolframclient` is pure-Python and ships in the image, but it
# drives a LOCAL Wolfram Engine kernel (`WolframKernel.exe` / the platform
# binary) that is NOT present inside this container. Where the kernel is absent
# the WolframService degrades to the LABELED `numeric_fallback` (§5.2, §11.1) —
# that is acceptable and honest, never presented as Wolfram. To run with a real
# kernel, mount/install the Engine on the host and point `WOLFRAM_KERNEL_PATH`
# at it (and run the backend where that kernel exists).
#
# Migrations are NOT run in this image's CMD — they run as a separate release /
# compose step (`alembic upgrade head`) per §9.4 / §11.1.

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential is ONLY needed here to build scipy/asyncpg wheels; it never
# lands in the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolated virtualenv so the runtime stage copies a single, self-contained tree.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

# Non-root user (§11.1). The app owns only its working tree.
RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app

# Copy the prebuilt virtualenv from the builder (no compilers in runtime).
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Application source. The backend's imports are top-level (`from models ...`,
# `from services ...`), so the package root IS the backend directory.
COPY backend/ /app/

RUN chown -R app:app /app
USER app

EXPOSE 8000

# Lightweight container healthcheck against the liveness probe (§3 /health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else sys.exit(1)"

# Migrations run as a separate release/compose step — NOT here (§11.1).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
