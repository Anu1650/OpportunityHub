# Expose the locally-running app to the internet via a Cloudflare quick tunnel.
#
# DEMO-DAY BACKUP ONLY. The trycloudflare.com URL is EPHEMERAL:
#   - it changes every time this script restarts
#   - it dies when you close the laptop or the terminal
#   - it does NOT satisfy the "Google Cloud Run URL" submission requirement
#
# Usage:  .\run-tunnel.ps1
# 1) start run-local.ps1 in one terminal
# 2) run this in a second terminal
# 3) keep BOTH terminals open. The public URL is printed below.

$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host @"
cloudflared is not installed. Install it with either:
  winget install --id Cloudflare.cloudflared
  or: choco install cloudflared
Then re-run this script.
"@ -ForegroundColor Yellow
    exit 1
}

# Confirm the app is actually up before tunnelling, so a blank tunnel
# URL does not get mistaken for a working demo.
try {
    $health = Invoke-RestMethod "http://127.0.0.1:8080/healthz" -TimeoutSec 5
    Write-Host "Local app healthy: $($health.listings) listings, store=$($health.store)" -ForegroundColor Green
} catch {
    Write-Host "No app on :8080 - start run-local.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "`nTunnelling... the public URL is printed below.`nKeep this window OPEN or the site goes down.`n" -ForegroundColor Cyan
cloudflared tunnel --url http://127.0.0.1:8080
