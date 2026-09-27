# Download the cloudflared binary into tools\. Run once.
#
# Needed because winget and choco are not always available, and Cloudflare's
# own install docs assume a package manager.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    Write-Host "cloudflared already on PATH: $((cloudflared --version) -join '')" -ForegroundColor Green
    exit 0
}

if (Test-Path ".\tools\cloudflared.exe") {
    Write-Host "tools\cloudflared.exe already present: $((& .\tools\cloudflared.exe --version) -join '')" -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Force -Path tools | Out-Null
$url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
$out = ".\tools\cloudflared.exe"

Write-Host "Downloading $url" -ForegroundColor Cyan
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 300

Write-Host "Installed: $((& $out --version) -join '')" -ForegroundColor Green
Write-Host "tools\ is gitignored, so the binary is never committed." -ForegroundColor DarkGray
