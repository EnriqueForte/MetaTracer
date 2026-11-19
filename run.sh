#!/usr/bin/env bash
# MetaTracer app launcher (Linux / Parrot / Debian). TASK-56.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtualenv not found. Run ./install.sh first." >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/desktop.py" run "$@"
