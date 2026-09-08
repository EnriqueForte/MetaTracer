#!/bin/sh
# MetaTracer Docker entrypoint (TASK-07, subtask 7.3.1).
#
#   web [uvicorn args...]  -> serve the API + Web UI via uvicorn
#   anything else          -> passed verbatim to the metatracer CLI
#
# The app reads METATRACER_* variables from the environment; secrets are
# injected at runtime (docker run -e / compose environment), never baked in.
set -e

if [ "${1:-}" = "web" ]; then
    shift
    exec /opt/venv/bin/uvicorn --factory metatracer.api.app:create_app \
        --host "${METATRACER_BIND_HOST:-0.0.0.0}" \
        --port "${METATRACER_PORT:-8000}" "$@"
fi

exec /opt/venv/bin/metatracer "$@"
