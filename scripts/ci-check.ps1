# CI guardrail local (TASK-16, v2.2) - Windows PowerShell.
# Replica la barrera del workflow de PR: ruff + suite rápida ("not e2e").
# Exit code != 0 si algo falla. No requiere red, credenciales ni loopback.
$ErrorActionPreference = "Stop"

$Py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "ERROR: no se encuentra .venv\Scripts\python.exe - crea el virtualenv primero (ver README)." -ForegroundColor Red
    exit 1
}

Write-Host "==> [1/2] ruff check src tests" -ForegroundColor Cyan
& $Py -m ruff check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> [2/2] pytest -m 'not e2e' -q" -ForegroundColor Cyan
& $Py -m pytest -m "not e2e" -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "CI guardrail local: OK (ruff + suite rapida en verde)" -ForegroundColor Green
exit 0