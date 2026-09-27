# Auto-start the app + public tunnel when Windows logs in.
#
# Placed in the Startup folder by setup-autostart.ps1, so the public link comes
# back automatically after a reboot instead of needing manual steps.
#
# The tunnel prints a NEW random URL on every start. If you need one fixed
# link, use a NAMED Cloudflare tunnel instead (see the note in run-tunnel.ps1).

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$log = Join-Path $PSScriptRoot "tunnel.log"

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $log -Value $line -ErrorAction SilentlyContinue
}

Log "autostart: beginning"

# Fetch the tunnel binary if it is not there yet (no winget on this machine).
if (-not (Test-Path ".\tools\cloudflared.exe")) {
    Log "autostart: downloading cloudflared"
    try {
        New-Item -ItemType Directory -Force -Path tools | Out-Null
        Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile ".\tools\cloudflared.exe" -UseBasicParsing -TimeoutSec 300
        Log "autostart: cloudflared downloaded"
    } catch {
        Log "autostart: download FAILED - $($_.Exception.Message)"
    }
}

# Free a stale listener, or the new server cannot bind.
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Log "autostart: no virtualenv, run 'py -3.12 -m venv .venv' once"
    exit 1
}

Log "autostart: starting app"
# Redirect the app's output too. Without it, the OTP codes the app logs go to a
# minimised window and tests\test_public.py can never capture them.
$appOut = Join-Path $PSScriptRoot "server.log"
$appErr = Join-Path $PSScriptRoot "server.err"
Remove-Item $appOut, $appErr -ErrorAction SilentlyContinue

Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080" `
    -WindowStyle Minimized -RedirectStandardOutput $appOut -RedirectStandardError $appErr

# Wait for a real health check before tunnelling, so we never publish a URL
# for an app that is not serving yet.
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:8080/healthz" -TimeoutSec 3
        Log "autostart: app healthy, $($h.listings) listings, store=$($h.store)"
        $up = $true
        break
    } catch { }
}
if (-not $up) { Log "autostart: app never became healthy"; exit 1 }

Log "autostart: opening tunnel"
$cf = if (Get-Command cloudflared -ErrorAction SilentlyContinue) { "cloudflared" }
      elseif (Test-Path ".\tools\cloudflared.exe") { ".\tools\cloudflared.exe" }
      else { Log "autostart: cloudflared missing"; exit 1 }

# Keep the current URL in a file so it can be read without scraping logs.
# Output MUST be redirected: launched with no redirection, cloudflared's
# stdout goes to a minimised window and the URL is never captured.
$tunnelOut = Join-Path $PSScriptRoot "tunnel.log"
$tunnelErr = Join-Path $PSScriptRoot "tunnel.err"
Remove-Item $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue

Start-Process -FilePath $cf `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:8080", "--no-autoupdate", "--protocol", "http2" `
    -WindowStyle Minimized -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr

# Poll for the URL rather than sleeping a fixed amount: the quick-tunnel API
# can take anywhere from 3 to 40 seconds to hand one back, and a fixed sleep
# either wastes time or misses it entirely.
$url = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 3
    $raw = (Get-Content $tunnelOut -Raw -ErrorAction SilentlyContinue) +
           (Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue)
    $found = [regex]::Match($raw, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
    if ($found) { $url = $found; break }
    if ($raw -match 'failed to request quick Tunnel') { Log "autostart: tunnel request failed"; break }
}

if ($url) {
    $url | Set-Content ".\public-url.txt" -NoNewline
    Log "autostart: public url = $url"
} else {
    Log "autostart: tunnel started but the URL was not captured; check tunnel.err"
}
