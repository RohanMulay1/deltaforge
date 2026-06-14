#!/usr/bin/env bash
#
# DeltaForge — GCP VM provisioning (Ubuntu 22.04 LTS).
#
# Installs Python 3.11, the backend venv, and Caddy (auto-HTTPS reverse proxy),
# then generates + enables the systemd service and Caddyfile so the backend
# auto-restarts on crash/reboot ("no interruptions").
#
# Run from the repo root on the VM, AFTER installing + activating Wolfram Engine
# and creating the .env (see deploy/gcp/README.md):
#
#     sudo bash deploy/gcp/setup.sh <DOMAIN>
#
# where <DOMAIN> is your nip.io host, e.g.  34-93-1-2.nip.io  (dashes = your IP).
#
set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: pass your nip.io domain, e.g.  sudo bash deploy/gcp/setup.sh 34-93-1-2.nip.io" >&2
  exit 1
fi

# Resolve repo root + the invoking (non-root) user so systemd doesn't run as root.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_USER="${SUDO_USER:-$(whoami)}"
VENV="$REPO_ROOT/.venv"
ENV_FILE="$REPO_ROOT/.env"

echo "[*] Repo:   $REPO_ROOT"
echo "[*] User:   $RUN_USER"
echo "[*] Domain: $DOMAIN"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Create it first (see deploy/gcp/README.md)." >&2
  exit 1
fi

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[*] Installing system packages (python3.11, build tools, caddy) ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y software-properties-common curl git build-essential \
  debian-keyring debian-archive-keyring apt-transport-https

# Python 3.11 via deadsnakes (Ubuntu 22.04 ships 3.10).
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y python3.11 python3.11-venv python3.11-dev

# Caddy (official repo) — gives automatic Let's Encrypt TLS for the nip.io host.
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

# ── 2. Python venv + backend deps ─────────────────────────────────────────────
echo "[*] Creating venv + installing backend requirements ..."
sudo -u "$RUN_USER" python3.11 -m venv "$VENV"
sudo -u "$RUN_USER" "$VENV/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$VENV/bin/pip" install -r "$REPO_ROOT/backend/requirements.txt"

# ── 3. Locate the Wolfram kernel ──────────────────────────────────────────────
KERNEL="$(ls /usr/local/Wolfram/WolframEngine/*/Executables/WolframKernel 2>/dev/null | sort -V | tail -1 || true)"
if [[ -z "$KERNEL" ]]; then
  echo "WARNING: WolframKernel not found under /usr/local/Wolfram/WolframEngine/." >&2
  echo "         Install + activate Wolfram Engine first, then set WOLFRAM_KERNEL_PATH in .env." >&2
else
  echo "[*] Found Wolfram kernel: $KERNEL"
  if ! grep -q '^WOLFRAM_KERNEL_PATH=' "$ENV_FILE"; then
    echo "WOLFRAM_KERNEL_PATH=$KERNEL" >> "$ENV_FILE"
    echo "[*] Appended WOLFRAM_KERNEL_PATH to .env"
  fi
fi

# ── 4. systemd unit (auto-restart on crash/reboot) ────────────────────────────
echo "[*] Writing /etc/systemd/system/deltaforge.service ..."
cat > /etc/systemd/system/deltaforge.service <<UNIT
[Unit]
Description=DeltaForge API (FastAPI + Wolfram Engine kernel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_ROOT/backend
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
# Wolfram kernel startup can take ~15s; give it room before systemd gives up.
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

# ── 5. Caddy reverse proxy with auto-HTTPS ────────────────────────────────────
echo "[*] Writing /etc/caddy/Caddyfile (auto-TLS for $DOMAIN) ..."
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	reverse_proxy 127.0.0.1:8000 {
		# Stream Server-Sent Events without buffering (the /analyze/stream endpoint).
		flush_interval -1
	}
}
CADDY

# ── 6. Start everything ───────────────────────────────────────────────────────
echo "[*] Enabling + starting services ..."
systemctl daemon-reload
systemctl enable deltaforge
systemctl restart deltaforge
systemctl reload caddy || systemctl restart caddy

echo
echo "==================================================================="
echo "  DeltaForge backend is up behind:  https://$DOMAIN"
echo "  Verify:   curl https://$DOMAIN/health/wolfram"
echo "  Logs:     journalctl -u deltaforge -f"
echo "  Set in Vercel:  NEXT_PUBLIC_API_URL=https://$DOMAIN"
echo "==================================================================="
