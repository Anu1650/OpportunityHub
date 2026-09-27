# Install (or remove) the Windows Startup entry that brings the app and the
# public tunnel back after every reboot.
#
# Usage:
#   .\setup-autostart.ps1          install
#   .\setup-autostart.ps1 -Remove  uninstall
#
# How it works: a shortcut to autostart.ps1 is placed in the Startup folder,
# so the app and tunnel start on every Windows log-in. The public URL is
# written to public-url.txt and appended to tunnel.log.
#
# Note: a quick tunnel gets a NEW random URL every time it starts. If you need
# one fixed link, use a NAMED Cloudflare tunnel -- see README.

param([switch]$Remove)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$startup = [Environment]::GetFolderPath('Startup')
$link = Join-Path $startup "OpportunityHub.lnk"
$script = Join-Path $PSScriptRoot "autostart.ps1"

if ($Remove) {
    if (Test-Path $link) {
        Remove-Item $link -Force
        Write-Host "Removed: $link" -ForegroundColor Yellow
    } else {
        Write-Host "Nothing to remove - no startup shortcut found." -ForegroundColor Yellow
    }
    exit 0
}

if (-not (Test-Path $script)) { throw "autostart.ps1 not found next to this script." }

# A .ps1 cannot be run directly from Startup, so create a shortcut that calls
# powershell with execution policy bypass (common local dev friction).
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = "powershell.exe"
$sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$sc.WorkingDirectory = $PSScriptRoot
$sc.Description = "Start OpportunityHub and its public Cloudflare tunnel"
$sc.WindowStyle = 7   # minimised
$sc.Save()

Write-Host "Installed startup entry:" -ForegroundColor Green
Write-Host "  $link"
Write-Host ""
Write-Host "On every Windows log-in it will:" -ForegroundColor Cyan
Write-Host "  1. download tools\cloudflared.exe if missing"
Write-Host "  2. start the app on 127.0.0.1:8080"
Write-Host "  3. wait for a health check"
Write-Host "  4. open the tunnel and save the URL to public-url.txt"
Write-Host ""
Write-Host "Read the current URL with:  Get-Content .\public-url.txt" -ForegroundColor Yellow
Write-Host "Remove it again with:      .\setup-autostart.ps1 -Remove" -ForegroundColor DarkGray
