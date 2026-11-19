#!/usr/bin/env bash
# MetaTracer installer (Linux / Parrot / Debian). TASK-56.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

pick_python() {
  local candidate
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)'; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if ! PY="$(pick_python)"; then
  echo "ERROR: MetaTracer needs Python 3.11 or 3.12." >&2
  echo "Parrot/Debian: sudo apt install python3.12 python3.12-venv python3-pip nodejs npm" >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/desktop.py" install "$@"
