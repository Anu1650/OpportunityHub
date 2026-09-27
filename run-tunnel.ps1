# Start the app AND a public Cloudflare tunnel, then print the public URL.
#
# DEMO-DAY BACKUP. The trycloudflare.com URL is EPHEMERAL:
#   - it changes every time this script restarts
#   - it dies when you close the laptop
#   - it does NOT satisfy the "Google Cloud Run URL" submission requirement
#
# The app uses the file backend (DB_BACKEND=file in .env), so accounts and
# bookmarks survive restarts. Do NOT use the file backend on Cloud Run -- its
# container filesystem is ephemeral.
#
# Usage:  .\run-tunnel.ps1
# Keep this window OPEN, or the public link goes down.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No virtualenv. Run: py -3.12 -m venv .venv" }

# cloudflared may be on PATH, or downloaded into tools\ by fetch-cloudflared.ps1
$cf = if (Get-Command cloudflared -ErrorAction SilentlyContinue) { "cloudflared" }
      elseif (Test-Path ".\tools\cloudflared.exe") { ".\tools\cloudflared.exe" }
      else { $null }

if (-not $cf) {
    Write-Host "cloudflared not found. Run .\fetch-cloudflared.ps1 first." -ForegroundColor Yellow
    exit 1
}

# Free a stale listener, or the new server silently fails to bind.
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Write-Host "Starting app on 127.0.0.1:8080 ..." -ForegroundColor Cyan
$job = Start-Process -FilePath $py `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080" `
    -PassThru -NoNewWindow

# Confirm the app is really up before tunnelling, so a dead URL is not mistaken
# for a working demo.
$up = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:8080/healthz" -TimeoutSec 3
        Write-Host "  app healthy: $($h.listings) listings, store=$($h.store)" -ForegroundColor Green
        $up = $true
        break
    } catch { }
}
if (-not $up) {
    Write-Host "App failed to start. Stopping." -ForegroundColor Red
    Stop-Process -Id $job.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "`nOpening Cloudflare tunnel - the public URL is printed below." -ForegroundColor Cyan
Write-Host "KEEP THIS WINDOW OPEN or the public link dies.`n" -ForegroundColor Yellow
& $cf tunnel --url http://127.0.0.1:8080 --no-autoupdate --protocol http2
