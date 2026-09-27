# Start the app locally on http://localhost:8080
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Free a stale listener, otherwise the new server fails to bind silently.
Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No virtualenv found. Run: py -3.12 -m venv .venv" }

Write-Host "Starting OpportunityHub on http://localhost:8080" -ForegroundColor Cyan
& $py -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload
