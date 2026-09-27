# Start the app locally on http://localhost:8080
# NOTE: single worker on purpose. The in-memory store is per-process.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No virtualenv found. Run: py -3.12 -m venv .venv" }

Write-Host "Starting OpportunityHub on http://localhost:8080" -ForegroundColor Cyan
& $py -m uvicorn main:app --host 127.0.0.1 --port 8080 --reload
