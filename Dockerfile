# syntax=docker/dockerfile:1
# MetaTracer image (TASK-07, subtask 7.3.1): multi-stage, non-root, minimal surface.
# Aligned with requires-python = ">=3.11,<3.13".

########## Builder: install the project into an isolated venv ##########
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Packaging files first (better layer caching); src changes most often, last.
COPY pyproject.toml README.md ./
COPY src ./src
# Closed dependency list (TASK-00): everything resolves from pyproject.toml.
RUN pip install .

########## Runtime: no toolchain, non-root user, only what runtime needs ##########
FROM python:3.12-slim AS runtime

# Runtime system libraries only: libjpeg + zlib (image metadata path).
# No compilers, no -dev headers, nothing else (supply-chain rule, threat 15).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system metatracer \
 && useradd --system --gid metatracer --create-home metatracer

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY docker/entrypoint.sh /app/docker-entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    METATRACER_DATABASE_URL="sqlite+aiosqlite:////app/data/metatracer.db" \
    METATRACER_BIND_HOST="0.0.0.0"

# Only these two host paths are ever mounted: ./data and ./reports.
RUN mkdir -p /app/data /app/reports \
 && chown -R metatracer:metatracer /app

USER metatracer
EXPOSE 8000

# "web" -> uvicorn (API + Web UI); anything else -> the metatracer CLI.
ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["web"]

# Liveness: the container's OWN loopback — unrelated to the scan-time guard.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "import urllib.request, sys; r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); sys.exit(0 if r.status == 200 else 1)"]
