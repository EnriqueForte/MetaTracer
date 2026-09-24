# MetaTracer

AI-powered sensitive metadata discovery for **authorized** bug bounty and red team
engagements.

> **Authorized use only.** MetaTracer scans public assets of targets you are explicitly
> authorized to test (an in-scope bug bounty program, a written audit agreement, or your
> own assets). Every run requires an explicit scope confirmation; there is no hidden or
> insecure mode in the default distribution. The goal is to help programs **remove**
> sensitive metadata, not to exploit it.

## Status

Closed: **v1.0–v1.2** (safety core, ingestion, five detectors, heuristic risk
classification, optional LangGraph agent analysis with heuristic fallback, reports,
CLI + Web UI over one shared orchestrator) → **v2.0** platform (scopes, dashboard,
notifications) → **v2.1+** (feedback loop, light RAG) → **v2.2** integrations (outbound
webhooks, portable KB, bounty exports, CI guardrail, scope import) → **v2.3**
performance & UI polish (API rate limiting, request body cap, accessibility, shared UI
helpers, consistent states) → **v2.4** multi-engagement (union of saved scopes per run,
keyset-paginated run history). Closed: **v3.0** platform (headless watch with
deterministic deltas — `metatracer watch`; PostgreSQL+pgvector; basic auth with
session cookies, CSRF and operator/viewer roles — `METATRACER_AUTH_ENABLED`) and
**v3.1** (multi-user registration with first-run setup, admin panel and one-time
invitations; **Web UI redesign** — design system `.mt-*`, Tailwind compiled offline and
Alpine CSP vendored under `/static`, no CDN scripts). Full suite green, `ruff` clean,
coverage ≥85%.

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

The Web UI runs on Jinja2 + Alpine CSP 3.17.4 (vendored) + Tailwind 3.4.16 compiled
offline into `/static` with a custom `.mt-*` design system — no CDN scripts, no Node
build step. Security headers (CSP, frame/nosniff, HSTS) are applied by
`api/security_headers.py`.

SQLite (default, single writer) or PostgreSQL + pgvector (`METATRACER_DATABASE_URL=postgresql+asyncpg://...`,
Alembic-managed schema, optional parallel scans via `METATRACER_MAX_CONCURRENT_RUNS`). Optional
authentication for the Web UI/API: `METATRACER_AUTH_ENABLED=true` — first boot provisions an
operator via `METATRACER_AUTH_PASSWORD` or, if unset, a one-time setup token printed to the
console (`/setup`); session cookie HttpOnly + CSRF; viewer role read-only; invitations
(`METATRACER_INVITE_TTL_SECONDS`) open registration to invited users; the localhost CLI needs no
login. Roadmap: **v3.0** platform vision — watch/headless mode (done), PostgreSQL+pgvector
(done), basic auth (done) (`.aicontext/features/12-platform-v3.md`); **v3.1** — multi-user
registration and Web UI redesign (done).

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

# v3.0: headless watch — continuously re-scan a saved scope, reporting deltas.
# Scope-id first; --once runs one iteration and exits; --interval is the cadence.
.venv\Scripts\python.exe -m metatracer watch <scope-id> --once
.venv\Scripts\python.exe -m metatracer watch <scope-id> --interval 21600 --webhook <webhook-id>
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

# v3.0 watch as a long-running container command (one watch per scope):
.\scripts\docker-metatracer.ps1 watch <scope-id> --interval 21600
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
