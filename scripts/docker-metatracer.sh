#!/bin/sh
# Ephemeral MetaTracer CLI inside Docker (TASK-07, subtask 7.3.4).
#
# Reports land in ./reports on the host and the container is deleted on exit
# (--rm). The run's SQLite database lives and dies inside the container; add
# -v "$(pwd)/data:/app/data" to keep run history.
#
# The METATRACER_LLM_* variables are passed through from the host environment;
# without them the run uses the heuristic classifier only.
# METATRACER_ALLOW_LOOPBACK is a test-only flag and is NOT passed through.
#
# Usage: ./scripts/docker-metatracer.sh scan example.com -s example.com -y
set -e

REPORTS_DIR="$(pwd)/reports"
mkdir -p "$REPORTS_DIR"

exec docker run --rm -it \
    -v "$REPORTS_DIR:/app/reports" \
    -e METATRACER_LLM_API_KEY \
    -e METATRACER_LLM_BASE_URL \
    -e METATRACER_LLM_MODEL \
    -e METATRACER_FAST_MODEL \
    metatracer "$@"
