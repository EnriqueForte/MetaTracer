#!/usr/bin/env bash
# CI guardrail local (TASK-16, v2.2) - Unix/macOS.
# Replica la barrera del workflow de PR: ruff + suite rápida ("not e2e").
# Exit code != 0 si algo falla. No requiere red, credenciales ni loopback.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: no se encuentra .venv/bin/python - crea el virtualenv primero (ver README)." >&2
  exit 1
fi

echo "==> [1/2] ruff check src tests"
"$PY" -m ruff check src tests

echo "==> [2/2] pytest -m 'not e2e' -q"
"$PY" -m pytest -m "not e2e" -q

echo ""
echo "CI guardrail local: OK (ruff + suite rapida en verde)"