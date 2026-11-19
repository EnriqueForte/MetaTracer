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
session cookies, CSRF and operator/viewer roles — `METATRACER_AUTH_ENABLED`),
**v3.1** (multi-user registration with first-run setup, admin panel and one-time
invitations; **Web UI redesign** — design system `.mt-*`, Tailwind compiled offline; the
Alpine build served from `/static` was the V1 asset and is gone since T11) and **v3.2** (hardening after the
2026-10-03 audit, TASK-27 → TASK-35: `trust_env=False`, auth-required public bind,
webhook HMAC, CSV formula neutralization, XMP pre-inflate cap, run recovery/abort,
agent output integrity, GDPR retention, API authz, webhook retries, detector precision,
Web V2 UX).

Suite verified on 2026-10-23: **787 passed, 6 skipped** (e2e included, loopback test
flag); coverage **91.30%** on core/detectors/extractors/reports (DoD ≥85%); `ruff`
clean. PostgreSQL integration tests skip when no server is reachable (local Docker redir
not supported). Fast loop re-verified on 2026-10-25: **751 passed, 6 skipped**
(`pytest -m "not e2e"`).

See `.aicontext/tasks/`. Architecture tour (Spanish): `.aicontext/walkthrough.md`.

## How it works

One pipeline, two surfaces (CLI and Web UI). Detection is deterministic; the LLM only
interprets.

1. **Safety gate** — no HTTP until the operator confirms scope. Private/loopback
   addresses are blocked. Every request goes through `safe_httpx_request`
   (`trust_env=False`: `HTTP(S)_PROXY` / `ALL_PROXY` are ignored). A download
   sends HEAD first (redirects included, each hop checked) and then GET of the
   already validated final URL, so the chain is not fetched twice. The leftover
   cost is one HEAD per hop plus one GET. `METATRACER_ALLOW_LOOPBACK` is ignored
   outside pytest: `scan`, `serve` and `watch` refuse to start.
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
7. **Triage** — an operator marks a finding `open`, `confirmed`, `false_positive` or
   `fixed` (`PUT /api/runs/<id>/findings/<finding_id>/triage`, `metatracer findings
   triage <finding_id> --status false_positive`, or the finding panel in Web V2). Triage
   never changes severity or evidence. False positives are left out of every export
   (`--include-false-positives` / `include_false_positives=true` keeps them) and of the
   dashboard counts, which show them as **Dismissed**. Watch deltas and
   `GET /api/compare?a=<run>&b=<run>` match findings across runs by asset URL, type and
   evidence.

The Web UI is **Web V2** (`web/`): Next.js 16 + React 19 + Tailwind 4, TypeScript
strict, TanStack Query for server data and Zod at form boundaries. It serves from the
origin root; FastAPI is API-only (since T11 the Jinja/Alpine Web V1 is gone). Features:
filters in the URL, a command palette (Ctrl/⌘+K), keyboard shortcuts (`?` lists them),
a GPS map drawn locally (no map tiles), run comparison, Webhooks and Knowledge screens
for operators, finding triage, and a System / Dark / Light theme switch. Security
headers for the API come from `api/security_headers.py`; the app shell's come from
`web/next.config.ts`. `GET /api/ready` checks the database; `/api/health` stays a
stateless liveness probe. One origin is served by Caddy in production
(`deploy/Caddyfile`), so the session cookie (`SameSite=Lax`) and the CSP
(`connect-src 'self'`) keep working.

SQLite (default, single writer) or PostgreSQL + pgvector (`METATRACER_DATABASE_URL=postgresql+asyncpg://...`,
Alembic-managed schema, optional parallel scans via `METATRACER_MAX_CONCURRENT_RUNS`). Optional
authentication for the Web UI/API: `METATRACER_AUTH_ENABLED=true` — first boot provisions an
operator via `METATRACER_AUTH_PASSWORD` or, if unset, a one-time setup token printed to the
console (`/setup`); session cookie HttpOnly + CSRF; viewer role read-only; invitations
(`METATRACER_INVITE_TTL_SECONDS`) open registration to invited users; the localhost CLI needs no
login. One installation is a single trust domain: every authenticated user sees every
run. Viewers cannot list users, invitations or webhook configuration, and cannot
export the knowledge base. An operator can delete a finished run
(`DELETE /api/runs/<id>`, `metatracer runs delete <id>`, or Delete run in the
history). `METATRACER_RETENTION_DAYS` deletes terminal runs older than that many
days; watch deltas then use only the runs that remain, so a pruned baseline can
surface old findings as new. `METATRACER_MAX_AGENT_FINDINGS` (default 50) caps how
many findings are sent to the model, separate from the download cap; the same
evidence on two assets is one model call. `METATRACER_LLM_CONCURRENCY` (default 1)
limits in-flight model calls and still honors the per-call rate limit.
`metatracer serve` on `127.0.0.1` still starts with auth off. Binding a non-loopback
address (Docker publishes `0.0.0.0:8000`) refuses to start unless auth is on or
`METATRACER_ALLOW_UNAUTHENTICATED_BIND=true` (logged warning; scope and the network guard stay
on). Compose defaults auth to **true**. If `.env` sets `METATRACER_AUTH_ENABLED=false`, Compose
uses that value and the container exits until you enable auth or the override. Roadmap: **v3.0**
platform vision — watch/headless mode (done), PostgreSQL+pgvector (done), basic auth (done)
(`.aicontext/features/12-platform-v3.md`); **v3.1** — multi-user registration and Web UI redesign
(done); **v3.2** — hardening after the 2026-10-03 audit, TASK-27 → TASK-35 (all closed;
suite verified 787 passed / coverage 91.30%).

## Requirements

- Python 3.11 or 3.12 (3.13+ is not supported)
- Node.js 20 or newer (Web UI)
- Git
- Or Docker, see below

## Install (Windows and Linux)

Clone the repo, run the **installer**, then the **app** launcher. The installer
creates `.venv`, installs the Python package and the Web UI (`npm ci`). The
launcher starts the API on `http://127.0.0.1:8000` and the UI on
`http://127.0.0.1:3000`.

### Windows

```powershell
git clone <this-repository>
cd MetaTracer
.\install.cmd
.\MetaTracer.cmd
```

`install.cmd` and `MetaTracer.cmd` are also double-clickable. If Python or Node
are missing, the installer prints the `winget` commands and exits.

### Linux (Debian, Parrot)

```bash
git clone <this-repository>
cd MetaTracer
chmod +x install.sh run.sh   # or: bash install.sh
./install.sh
./run.sh
```

If Python 3.11/3.12 or Node.js are missing:

```bash
sudo apt install python3.12 python3.12-venv python3-pip nodejs npm git
```

Then run `./install.sh` again. Stop the app with Ctrl+C.

Contributor extras (`pytest`, `ruff`): `./install.sh --dev` or
`.\install.cmd --dev`.

### Manual venv (optional)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

On Linux/Parrot use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

## Verify

```powershell
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m pytest tests -v
```

## Usage

```powershell
# App launcher (API :8000 + Web UI :3000) — prefer this after a clone
.\MetaTracer.cmd          # Windows
# ./run.sh                # Linux / Parrot

# CLI (scope is never inferred; -y confirms authorization non-interactively)
.venv\Scripts\python.exe -m metatracer scan example.com -s example.com -y

# API only (no Web V2). The full UI is MetaTracer.cmd / ./run.sh
.venv\Scripts\python.exe -m metatracer serve

# Stop a scan from the CLI with Ctrl+C. The run is stored as aborted, not failed.
# From the API (operator + CSRF): POST /api/runs/<run-id>/abort
# A restart marks leftover pending/running runs aborted
# ("interrupted: process restarted") when they started before this process.

# v3.0: headless watch — continuously re-scan a saved scope, reporting deltas.
# Scope-id first; --once runs one iteration and exits; --interval is the cadence.
.venv\Scripts\python.exe -m metatracer watch <scope-id> --once
.venv\Scripts\python.exe -m metatracer watch <scope-id> --interval 21600 --webhook <webhook-id>
```

## Docker

Multi-stage image on `python:3.12-slim` with a non-root `metatracer` user. The
entrypoint accepts `web` (uvicorn serving the API + Web UI) or passes its
arguments verbatim to the CLI.

Since **T10** the default `docker compose up` starts **three** services behind a
single origin, so the browser sees one host for the session cookie
(`SameSite=Lax`) and the CSP (`connect-src 'self'`):

| Service | Role |
| :--- | :--- |
| `web` | FastAPI: JSON API and SSE. Not published; reachable only from the proxy. |
| `web-v2` | Next.js (Web V2): the product UI. No secrets, no DB. |
| `proxy` | Caddy. Routes `/api/*` and `/static/*` → `web`; everything else → `web-v2`. |

The Python image still does **not** contain Node (`web/` is in `.dockerignore`);
Web V2 is a separate image. `deploy/Caddyfile` disables proxy buffering on
`/api/*` so `GET /api/runs/{id}/stream` stays live.

```powershell
docker build -t metatracer .

# Web UI + API on http://localhost:8000 (all of it is Web V2); ./data and
# ./reports persist on the host
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
classifier only. The `web` command checks the bind address before uvicorn
starts (see authentication above).

## Webhook signatures

A webhook created with `signature_secret` signs every delivery. The API never
returns the secret. Headers:

- `X-MetaTracer-Timestamp` — Unix time in seconds
- `X-MetaTracer-Signature` — `sha256=<hex>`

The MAC is HMAC-SHA256 of the UTF-8 string `{timestamp}.{body}`, where `body`
is the raw request body: compact JSON (`separators=(",", ":")`), keys sorted,
UTF-8. Verify those exact bytes; do not re-encode the JSON. Reject timestamps
outside a window you choose (five minutes is a reasonable start) to limit
replay.

Configs created before TASK-27 stored only a hash of the secret. They are
delivered **unsigned** until you set the secret again. `GET /api/webhooks`
reports `signature_status`: `active`, `needs_secret`, or `none`.

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
- `src/metatracer/services/`, `cli/`, `api/` — shared orchestrator, Typer CLI, FastAPI API
  (API-only since T11; the UI lives in `web/`)
- `tests/` — `unit/`, `integration/` (incl. e2e), `agents/`, `fixtures/` (see
  `tests/README.md` for marks and the loopback test flag)
- `data/` — runtime SQLite database (git-ignored)
- `reports/` — exported reports (git-ignored)
