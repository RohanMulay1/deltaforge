<#
  run-and-tunnel.ps1 - DeltaForge "Free path 2" launcher.

  Boots the real backend (local Wolfram Engine kernel) if it isn't already
  running, opens a free Cloudflare quick-tunnel to it, and prints the public
  https URL to paste into your frontend's NEXT_PUBLIC_API_URL.

  Usage:   powershell -ExecutionPolicy Bypass -File .\run-and-tunnel.ps1
  Stop:    Ctrl+C  (cleans up anything this script started)
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8000
$healthUrl = "http://127.0.0.1:$port/health"

# Defaults (the backend also reads .env; these only fill gaps).
if (-not $env:WOLFRAM_KERNEL_PATH) {
  $env:WOLFRAM_KERNEL_PATH = "C:\Program Files\Wolfram Research\Wolfram Engine\14.3\WolframKernel.exe"
}
if (-not $env:WOLFRAM_POOL_SIZE) { $env:WOLFRAM_POOL_SIZE = "1" }

function Test-Health {
  try { (Invoke-WebRequest -Uri $healthUrl -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 }
  catch { $false }
}

function Write-Banner($url) {
  Write-Host ""
  Write-Host "===================================================================" -ForegroundColor DarkYellow
  Write-Host "  DeltaForge backend is PUBLIC at:" -ForegroundColor Yellow
  Write-Host "      $url" -ForegroundColor Green
  Write-Host ""
  Write-Host "  Next steps:" -ForegroundColor Yellow
  Write-Host "    1. Frontend env:  NEXT_PUBLIC_API_URL=$url"
  Write-Host "    2. Backend CORS:  add your frontend URL to CORS_ALLOW_ORIGINS in .env, then restart"
  Write-Host "    3. Check kernel:  $url/health/wolfram  (expect engine_in_use: wolfram)"
  Write-Host ""
  Write-Host "  Live only while this window is open. Ctrl+C to stop." -ForegroundColor DarkGray
  Write-Host "===================================================================" -ForegroundColor DarkYellow
  Write-Host ""
}

$backendProc = $null
$cfProc = $null
$startedBackend = $false

try {
  # ── 1. Backend ────────────────────────────────────────────────────────────
  if (Test-Health) {
    Write-Host "[ok] Backend already running on :$port - reusing it." -ForegroundColor Green
  } else {
    $py = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    Write-Host "[..] Starting backend (real Wolfram kernel) on :$port ..." -ForegroundColor Cyan
    $backendProc = Start-Process -FilePath $py `
      -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$port", "--log-level", "warning") `
      -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Hidden
    $startedBackend = $true

    $up = $false
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Seconds 2
      if (Test-Health) { $up = $true; break }
      if ($backendProc.HasExited) { throw "Backend process exited during startup (exit $($backendProc.ExitCode)). Check deps / .env." }
    }
    if (-not $up) { throw "Backend did not become healthy on :$port within ~80s." }
    Write-Host "[ok] Backend healthy." -ForegroundColor Green
  }

  # Report kernel state
  try {
    $w = (Invoke-WebRequest -Uri "$healthUrl/wolfram" -TimeoutSec 5 -UseBasicParsing).Content | ConvertFrom-Json
    $engine = $w.engine_in_use
    if ($engine -eq "wolfram") { Write-Host "[ok] Wolfram kernel LIVE (engine_in_use: wolfram)." -ForegroundColor Green }
    else { Write-Host "[warn] engine_in_use: $engine (kernel not live - check WOLFRAM_KERNEL_PATH / orphaned kernels)." -ForegroundColor Yellow }
  } catch { Write-Host "[warn] couldn't read /health/wolfram." -ForegroundColor Yellow }

  # ── 2. cloudflared ────────────────────────────────────────────────────────
  $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
  if (-not $cf) {
    Write-Host "[..] cloudflared not found - installing via winget ..." -ForegroundColor Cyan
    winget install --id Cloudflare.cloudflared --silent --accept-source-agreements --accept-package-agreements
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) { throw "cloudflared install failed. Install it manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" }
  }

  Write-Host "[..] Opening Cloudflare tunnel ..." -ForegroundColor Cyan
  $log = Join-Path $env:TEMP "df-cloudflared.log"
  if (Test-Path $log) { Remove-Item $log -Force }
  $cfProc = Start-Process -FilePath $cf.Source `
    -ArgumentList @("tunnel", "--url", "http://localhost:$port") `
    -RedirectStandardError $log -RedirectStandardOutput "$log.out" -PassThru -WindowStyle Hidden

  # Poll the log for the public URL cloudflared prints.
  $publicUrl = $null
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
      $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($m) { $publicUrl = $m.Matches[0].Value; break }
    }
    if ($cfProc.HasExited) { throw "cloudflared exited early. Log: $log" }
  }
  if (-not $publicUrl) { throw "Tunnel URL not found in cloudflared output within ~30s. Log: $log" }

  Write-Banner $publicUrl

  # ── 3. Wait until the tunnel dies / Ctrl+C ────────────────────────────────
  while (-not $cfProc.HasExited) { Start-Sleep -Seconds 2 }
}
finally {
  Write-Host ""
  Write-Host "[..] Cleaning up ..." -ForegroundColor DarkGray
  if ($cfProc -and -not $cfProc.HasExited) { Stop-Process -Id $cfProc.Id -Force -ErrorAction SilentlyContinue }
  if ($startedBackend -and $backendProc -and -not $backendProc.HasExited) {
    Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    Write-Host "[ok] Stopped the backend this script started." -ForegroundColor DarkGray
  } else {
    Write-Host "[ok] Left the pre-existing backend running." -ForegroundColor DarkGray
  }
}
