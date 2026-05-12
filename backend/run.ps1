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
    Write-Warning "backend\.env is missing. Copy backend\.env.example to backend\.env and set GEMINI_API_KEY."
}

# Make sure no stale shell env var shadows the .env value.
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue

$port = 8000
if ($env:PORT -match '^[0-9]+$') {
    $port = [int]$env:PORT
} elseif ($env:PORT -and $env:PORT -notmatch '^[0-9]+$') {
    Write-Warning "Ignoring invalid PORT (use digits only, e.g. 8000; bash-style PORT syntax is not expanded in PowerShell). Using $port."
}

Write-Host "Starting FastAPI on http://127.0.0.1:$port (Ctrl+C to stop)" -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port $port --host 127.0.0.1
