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
    # TASK-27: a public bind with auth off must fail before the socket opens.
    # --host is last so a later argument cannot bind an address we did not check.
    /opt/venv/bin/python -c "from metatracer.core.bind_auth import enforce_public_bind_from_env; enforce_public_bind_from_env()"
    exec /opt/venv/bin/uvicorn --factory metatracer.api.app:create_app \
        --port "${METATRACER_PORT:-8000}" \
        "$@" \
        --host "${METATRACER_BIND_HOST:-0.0.0.0}"
fi

exec /opt/venv/bin/metatracer "$@"
