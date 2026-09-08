# MetaTracer

AI-powered sensitive metadata discovery for **authorized** bug bounty and red team
engagements.

> **Authorized use only.** MetaTracer scans public assets of targets you are explicitly
> authorized to test (an in-scope bug bounty program, a written audit agreement, or your
> own assets). Every run requires an explicit scope confirmation; there is no hidden or
> insecure mode in the default distribution. The goal is to help programs **remove**
> sensitive metadata, not to exploit it.

## Status

v1.2 complete (TASK-00 … TASK-09): safety core, ingestion (crawler + PDF/image
plus HTML pages, HTTP headers and JS comments), five metadata detectors, heuristic
risk classification, optional LangGraph agent analysis with heuristic fallback,
Markdown/JSON/HTML reports, and a CLI + Web UI over one shared orchestrator.
See `.aicontext/tasks/`. Architecture tour (Spanish): `.aicontext/walkthrough.md`.

## How it works

One pipeline, two surfaces (CLI and Web UI). Detection is deterministic; the LLM only
interprets.

1. **Safety gate** — no HTTP until the operator confirms scope. Private/loopback
   addresses are blocked. Every request goes through `safe_httpx_request`.
2. **Ingest** — depth-1 crawl. PDFs and images (magic-byte allowlist), the HTML page
   itself, recon HTTP headers (allowlist), and comments from in-scope `.js`. File bytes
   and HTML/JS bodies are never stored.
3. **Detect** — five finding types (`gps`, `email`, `internal_path`, `software_version`,
   `debug_comment`). Severity stays unset.
4. **Classify** — heuristic rubric with type ceilings (always available).
5. **Agents** (optional LangGraph) — one finding per call, short evidence snippets only.
   If the model fails, the heuristic baseline remains. The post-LLM guard can only lower
   or reject severity.
6. **Report** — Markdown, JSON and HTML in English, ordered Critical → Info.

SQLite now (single writer); schema is PostgreSQL-ready for later pgvector/RAG. Next
product phase is v2.0 (platform dashboard), not new finding types.

## Requirements

- Python >= 3.11, < 3.13 (or Docker, see below)

## Install

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Verify

```powershell
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m pytest tests -v
```

## Usage

```powershell
# CLI (scope is never inferred; -y confirms authorization non-interactively)
.venv\Scripts\python.exe -m metatracer scan example.com -s example.com -y

# Web UI + API on http://127.0.0.1:8000
.venv\Scripts\python.exe -m metatracer serve
```

## Docker

Multi-stage image on `python:3.12-slim` with a non-root `metatracer` user. The
entrypoint accepts `web` (uvicorn serving the API + Web UI) or passes its
arguments verbatim to the CLI.

```powershell
docker build -t metatracer .

# Web UI + API on http://localhost:8000; ./data and ./reports persist on the host
docker compose up --build

# Ephemeral CLI: reports land in .\reports and the container is deleted on exit
.\scripts\docker-metatracer.ps1 scan example.com -s example.com -y
# bash equivalent: ./scripts/docker-metatracer.sh scan example.com -s example.com -y
```

The container keeps the default safety posture: `METATRACER_ALLOW_LOOPBACK` is a
test-only flag and is **not** set by the image or the Compose file. The image
healthcheck is `GET /api/health`. The ephemeral CLI passes the host's
`METATRACER_LLM_*` variables through; without them the run uses the heuristic
classifier only.

## Configuration

Copy `.env.example` to `.env` and adjust. Every variable uses the `METATRACER_` prefix.
`METATRACER_ALLOW_LOOPBACK` exists **only for the test suite** (local mock server); never
enable it anywhere else.

## Layout

- `src/metatracer/core/` — configuration, logging, exceptions, safety core
  (`safety/scope.py`, `safety/guard.py`, `safety/http.py`)
- `src/metatracer/db/` — async engine, SQLModel models, CRUD repositories
- `src/metatracer/extractors/` — ingestion pipeline, crawler, PDF/image/HTML/JS/header extractors
- `src/metatracer/detectors/` — the five metadata detectors + dedup consolidation
- `src/metatracer/classification/` — severity rubric + heuristic classifier
- `src/metatracer/agents/` — LangGraph agent loop, evidence guard, heuristic fallback
- `src/metatracer/reports/` — Markdown/JSON exporters
- `src/metatracer/services/`, `cli/`, `api/` — shared orchestrator, Typer CLI, FastAPI UI
- `tests/` — `unit/`, `integration/` (incl. e2e), `agents/`, `fixtures/` (see
  `tests/README.md` for marks and the loopback test flag)
- `data/` — runtime SQLite database (git-ignored)
- `reports/` — exported reports (git-ignored)
