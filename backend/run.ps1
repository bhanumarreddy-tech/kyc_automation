# Convenience launcher for the FastAPI backend.
# Usage from the repo root:
#   .\backend\run.ps1
# Or double-click this file in Explorer (right-click -> Run with PowerShell).

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Virtualenv not found at backend\.venv. Run 'python -m venv .venv' and 'pip install -r requirements.txt' first."
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Warning "backend\.env is missing. Copy backend\.env.example to backend\.env and set ANTHROPIC_API_KEY."
}

# Make sure no stale shell env var shadows the .env value.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

Write-Host "Starting FastAPI on http://127.0.0.1:8000 (Ctrl+C to stop)" -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
