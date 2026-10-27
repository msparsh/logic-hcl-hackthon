# Starts the API and the UI for the demo (Windows PowerShell).
# Run from the repository root after setup:  .\scripts\run_demo.ps1
# Backend:  http://127.0.0.1:8000/docs     UI:  http://localhost:8501

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Run: python scripts/create_instant_db.py" -ForegroundColor Red
    exit 1
}

$activate = Join-Path $root ".venv\Scripts\Activate.ps1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$activate'; python -m uvicorn app.api:app --port 8000"
Start-Sleep -Seconds 4
& $activate
python -m streamlit run streamlit_app.py
