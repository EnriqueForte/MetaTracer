---
name: metatracer-platform
description: Superficie de plataforma ya existente en MetaTracer (watch/delta, Postgres/Alembic/pgvector hashing-trick, auth/CSRF, webhooks HMAC, triage, retención, conectores). Usar al tocar watch, db/engine, Alembic, auth, webhooks, triage, retención o connectors/ — no para rediseñar v3.0 ni implementar specs reserved.
---

# Plataforma existente (v3.0–v3.2)

Evita que un agente reimplemente lo que TASK-22–45 ya cerraron. Deltas watch
desaparecido/severity-up: [spec 50](../../../specs/50-watch-deltas.md) **reserved**
(no código hasta `active`).

Fuentes: `.aicontext/tasks/22-watch-headless.md` … `35-ui-ux-improvements.md`,
`.aicontext/features/12-platform-v3.md`. Safety: wrapper HTTP + anti-SSRF de egreso
siguen mandando.

## Watch (TASK-22)

- `metatracer watch` con `--once` / `--interval` / `--cron` (UTC, 5 campos, stdlib) /
  `--webhook`. `--cron` es exclusivo de `--interval` y de `--once`. Lock por scope.
- `DeltaReporter` determinista por `finding_identity`, **sin LLM**. Payload webhook:
  `new_findings` (solo hallazgos **nuevos**).
- Operación: `deploy/metatracer-watch.service` y compose profile `watch`.
- No está implementado: deltas “desaparecido / severity-up” — spec 50 reserved
  (`PAYLOAD_KEYS` no se amplía sin esa spec `active`).

## Postgres + pgvector (TASK-23)

- URL `postgresql+asyncpg`; pelada se rechaza. Alembic empaquetado, `init_db` lo corre.
- `PgVectorKnowledgeIndex`: embeddings 384-d. TASK-40 usa MiniLM ONNX local si
  hay extra `[onnx]` y `METATRACER_ONNX_MODEL_PATH`; si no, hashing-trick.
  Misma interfaz `KnowledgeRetriever`. Sin pgvector → no-op + warning.
- `METATRACER_MAX_CONCURRENT_RUNS` (default 1). Compose profile `postgres`.

## Auth (TASK-24/25)

- Cookie `HttpOnly` + CSRF double-submit. Roles `operator` / `viewer`.
- PBKDF2-SHA256 600k stdlib, token de sesión solo-hash. CLI **sin** login.
- Kill-switch `METATRACER_AUTH_ENABLED`. First-run setup, invitaciones, admin.
- Bind público exige auth (TASK-27 / ADR-0013).

## Webhooks (TASK-15, HMAC TASK-27)

- CRUD, relay buffer, retries, anti-SSRF en egreso. Secreto no se relee tras guardar.
- Firma HMAC real (ADR-0014). `trust_env=False` (ADR-0012).

## Triage y retención (TASK-35, TASK-30)

- `triage_status`: solo operador; no cambia `severity` ni evidencia. Default oculta
  `false_positive` en exports/conteos.
- Borrado de runs sin huérfanos; retención configurable.

## Conectores (TASK-38)

Lista cerrada: RDAP (`data.iana.org` + base HTTPS del bootstrap), Wayback CDX
(`web.archive.org`, sin `/web/`), Common Crawl index (`index.commoncrawl.org`,
sin WARC). Egreso: `ProviderClient` (HTTPS, sin redirects, `trust_env=False`,
`NetworkSafetyGuard`). El operador no añade hosts. Apagado (`enabled=False` /
`connector.status=disabled`) **no construye cliente ni abre socket**.
`degraded` = 429 (CC también 503 tras un retry). No forman parte del scan, así
que un 429 no tumba un run. HMAC sigue en webhooks, no en estos GET.

## Abort (TASK-28) y ops (TASK-41)

- Recovery de huérfanos al arrancar; abort cooperativo API/CLI/UI.
- Lock durable: `concurrency_gate` + recuento de `pending`/`running` en la misma transacción que el INSERT del run. El semáforo in-memory sigue en un proceso.
- Resume: `POST /api/runs/{id}/resume` y `metatracer resume` re-encolan un run **nuevo** desde el snapshot; el original sigue `aborted`.
- `GET /api/metrics` texto Prometheus (stdlib). Alias `/api/v1/*` → `/api/*`.

## Checklist

- [ ] No inventar un destino de conector nuevo sin supply-chain. ONNX = extra `[onnx]`, local.
- [ ] No añadir `apscheduler` ni Windows Service. Cron = stdlib UTC.
- [ ] Authz: mutaciones operator + CSRF; viewer lectura.
- [ ] Egreso: mismo guard anti-SSRF que el crawler, destinos no son scope de scan.
