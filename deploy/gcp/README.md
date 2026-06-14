# DeltaForge on a GCP VM — always-on, real Wolfram kernel

This runbook deploys the backend on a Google Compute Engine VM so it runs 24/7
(independent of your PC) **with the real Wolfram Engine kernel**, fronted by
automatic HTTPS. The Vercel frontend points at it via a stable URL.

```
Vercel (frontend, https)  ──https──▶  GCP VM (static IP)
                                        ├─ Caddy → auto-HTTPS at https://<ip-dashed>.nip.io
                                        ├─ DeltaForge backend (systemd, Restart=always)
                                        └─ Wolfram Engine → engine_in_use: wolfram
```

## ⚠️ Market data on a datacenter IP

Yahoo (`yfinance`) rate-limits datacenter IPs — **including GCP**. The VM fixes
*hosting* and *Wolfram*, but `yfinance` may still 429. For a reliable week, set
`MARKET_DATA_PROVIDER=tradier` (free developer token, serves real options
chains, datacenter-friendly). See "Market data" at the bottom.

---

## 1. Create the VM (GCP Console)

1. **Compute Engine → VM instances → Create instance.**
2. **Name:** `deltaforge` · **Region:** `asia-south1` (Mumbai) or closest to you.
3. **Machine type:** `e2-standard-2` (2 vCPU, 8 GB RAM). *Do not go below 4 GB —
   the Wolfram Engine needs headroom.*
4. **Boot disk:** Change → **Ubuntu 22.04 LTS**, size **30 GB**.
5. **Firewall:** tick **Allow HTTP traffic** and **Allow HTTPS traffic**.
6. **Create.**

### Reserve a static IP (so the URL never changes)
- **VPC network → IP addresses → External IP addresses.**
- Find the `deltaforge` row, change **Type** from *Ephemeral* to **Static**, name it.
- Note the IP, e.g. `34.93.1.2`. Your domain is that IP **with dashes**:
  `34-93-1-2.nip.io`.

## 2. SSH in
Click **SSH** next to the instance in the console (opens a browser terminal).

## 3. Get the code onto the VM
The repo is private, so clone with a GitHub Personal Access Token (Settings →
Developer settings → Fine-grained tokens, read-only on this repo):

```bash
sudo mkdir -p /opt && sudo chown "$USER" /opt
cd /opt
git clone https://<YOUR_GH_TOKEN>@github.com/RohanMulay1/deltaforge.git
cd deltaforge
```

## 4. Install + activate Wolfram Engine
Download the free Engine for Linux (you're signed in with your Wolfram ID at
<https://www.wolfram.com/engine/>) — copy the Linux download link, then:

```bash
cd ~
wget -O WolframEngine.sh "<LINUX_DOWNLOAD_LINK>"
sudo bash WolframEngine.sh            # accept the default install path
# Activate with your Wolfram ID (interactive: enter email + password):
wolframscript -activate
wolframscript -code "1+1"             # must print 2
```

The installer puts the kernel at
`/usr/local/Wolfram/WolframEngine/<ver>/Executables/WolframKernel` — `setup.sh`
auto-detects it.

## 5. Create the `.env`
```bash
cd /opt/deltaforge
nano .env
```
Paste (the kernel path is auto-appended by setup.sh, so you can omit it):
```
GROQ_API_KEY=<your-groq-key>
DATABASE_URL=<your-supabase-session-pooler-url>
MARKET_DATA_PROVIDER=yfinance
WOLFRAM_POOL_SIZE=1
RISK_FREE_RATE=0.053
DELTA_TARGET=0.0
LOG_LEVEL=INFO
CORS_ALLOW_ORIGINS=https://deltaforge-seven.vercel.app
```
> Use the exact `GROQ_API_KEY` and `DATABASE_URL` values from your local
> `.env` (never commit them). Paste them straight into the VM's `.env`.

## 6. Run setup (installs deps, Caddy, systemd, starts everything)
```bash
sudo bash deploy/gcp/setup.sh 34-93-1-2.nip.io     # ← your dashed IP
```
It prints the public URL. Verify:
```bash
curl https://34-93-1-2.nip.io/health/wolfram        # expect engine_in_use: wolfram
journalctl -u deltaforge -f                          # live logs
```

## 7. Point Vercel at it (once)
Vercel → project → **Settings → Environment Variables**:
```
NEXT_PUBLIC_API_URL=https://34-93-1-2.nip.io
```
**Redeploy.** Done — the URL is permanent, the backend auto-restarts, your PC
can be off.

---

## Operations
| Task | Command |
|------|---------|
| Restart backend | `sudo systemctl restart deltaforge` |
| Backend logs | `journalctl -u deltaforge -f` |
| Backend status | `systemctl status deltaforge` |
| Reload Caddy | `sudo systemctl reload caddy` |
| Update code | `cd /opt/deltaforge && git pull && sudo systemctl restart deltaforge` |

## Cost
`e2-standard-2` ≈ **$0.067/hr ≈ $1.6/day ≈ ~$11 for a week** — well within the
$300 free-trial credit. A static IP is free while attached to a running VM.

## Market data (recommended for the week)
If `yfinance` 429s from the GCP IP, switch to Tradier:
1. Free token at <https://developer.tradier.com/> (or Sandbox).
2. In `.env`: `MARKET_DATA_PROVIDER=tradier` and `TRADIER_TOKEN=<token>`.
3. `sudo systemctl restart deltaforge`.

(The Tradier provider lands in `backend/providers/` — see the project changelog.)
