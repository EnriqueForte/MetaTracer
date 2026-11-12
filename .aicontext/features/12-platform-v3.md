# Plataforma v3.0 — visión y territorio (propuesta)

**Proyecto:** MetaTracer
**PRD:** [volver al índice](../PRD.md)
**Estado:** **Visión formalizada 2026-09-16; Eje A (watch/headless) implementado el mismo día ([TASK-22](../tasks/22-watch-headless.md)); Eje B (PostgreSQL + pgvector) implementado 2026-09-17 ([TASK-23](../tasks/23-postgres-pgvector.md)); Eje C (auth básica 1 usuario) implementado 2026-09-18 ([TASK-24](../tasks/24-auth-basic.md)) — v3.0 cerrada**. Multi-usuario e invitaciones → v3.1 ([TASK-25](../tasks/25-user-registration.md), cerrada 2026-09-19); rediseño de UI → [TASK-26](../tasks/26-ui-redesign.md) (aplicado 2026-09-21).

---

## 1. Por qué v3.0

El roadmap actual (v1.0–v2.3) entrega una herramienta local de un solo operador: SQLite single-writer, sin auth, un run/scan a la vez, contexto RAG con FTS5. Eso cubre el MVP y las integraciones. **v3.0 es el salto de "herramienta de auditoría local" a "plataforma de recon continua"**: el mismo motor, pero con *persistencia multiusuario* y *ejecución programada*.

Tres ejes, en orden de dependencia:

| Eje | Problema que resuelve | Palanca |
| :--- | :--- | :--- |
| A. **Modo watch/headless** | Un engagement real no es un scan puntual: es descubrir, reapuntar y reportar en el tiempo | `metatracer watch <scope> --cron "0 2 * * *"` + webhook por delta |
| B. **PostgreSQL + pgvector** | FTS5 (TASK-14) es léxico; el RAG real necesita vectores y un motor que soporte lecturas concurrentes | Cambiar unicamente `db/engine.py` + `agents/knowledge.py` (ya preparado) |
| C. **Auth + multi-usuario** | Hoy la seguridad es solo el bind a localhost; una plataforma se expone | Sesiones, roles (operator/viewer), bound de scopes por usuario |

---

## 2. Eje A — Modo watch (headless continuo)

**Objetivo:** un comando/daemon que re-escanea un scope con cadencia configurable y solo notifica **deltas** (nuevos findings, findings que desaparecen, severidad que sube).

> **Estado 2026-09-16 / cron 2026-11-05 / overlay 2026-11-12:** implementado como [TASK-22](../tasks/22-watch-headless.md) y [TASK-44](../tasks/44-watch-cron.md). `metatracer watch` con `--once`/`--interval`/`--cron` (UTC, stdlib)/`--webhook`, lock por scope, delta determinista y `new_findings` en el webhook. Pendiente del Eje A: "findings que desaparecen / severidad que sube" — [spec 50](../../specs/50-watch-deltas.md) **reserved** (ampliar `PAYLOAD_KEYS` solo con esa spec `active`).

Entregables:

- `metatracer watch --scope <id> --cron "job de 6h" --only-delta --webhook <id>`:
  - Reutiliza `ScanOrchestratorService` tal cual (mismo pipeline, mismo safety, mismo lock por run).
  - La "memoria" es la BD local: un run nuevo compara su `dedup_signature` set contra los runs anteriores del mismo scope.
  - Delta = findings nuevos (que no existían en ningún run previo con ese `(scope, asset, signature)`), determinista, sin LLM.
- **Programador**: primero `--interval` (bucle `asyncio.sleep`), y un `--cron` real como mejora (sin dependencia nueva: parseo crontab mini propio o `apscheduler` bajo revisión de la lista cerrada — **requiere aprobación** de supply-chain).
- **Notificación**: via TASK-15 (webhooks ya con retries y anti-SSRF) con `event=completed`.
  - El payload actual lleva `total_findings`; para delta, añadir un campo `new_findings` a `PAYLOAD_KEYS` (mismo contrato de payload plano) o un reporte diferencial.
- **Operación**:
  - Un solo watch por scope (lock por proceso/archivo).
  - En Docker, correr como segundo comando del mismo contenedor (`command: ["watch", "--scope", "...", "--interval", "6h"]`).
  - No reintenta en bucle descontrolado: backoff doble tras N scans fallidos (reusar la lógica de backoff de webhooks).

Rutas posibles de producto:
- Watch + webhook = **sentinel sin ser intrusivo**: es literalmente "recon alerting" que el cliente bug bounty aprecia.
- Watch + export = **reporte periódico automático** del engagement acoplado a GitHub issues (a través de webhook genérico, sin integración nueva).

---

## 3. Eje B — PostgreSQL + pgvector

> **Estado 2026-09-17:** implementado como [TASK-23](../tasks/23-postgres-pgvector.md). `postgresql+asyncpg` soportado en `create_db_engine` (driver exigido; URL pelada rechazada en el arranque), migraciones Alembic empaquetadas ejecutadas programáticamente en `init_db` (SQLite conserva su bootstrap legacy), `PgVectorKnowledgeIndex` con embeddings hashing-trick deterministas de 384 dims detrás de la misma interfaz `KnowledgeRetriever` (cero cambios en `AgentPipeline`; Postgres sin pgvector → no-op con warning), `METATRACER_MAX_CONCURRENT_RUNS` (default 1; >1 = semáforo) y compose profile `postgres`. Pendiente del Eje B: embeddings ONNX (`all-MiniLM-L6-v2`) — solo hay que sustituir `_embed`; la geometría 384 ya está reservada.

El código ya declara "PostgreSQL-ready" (UUIDs `str`, timestamps `DateTime(timezone=True)`, sin tipos exclusivos de SQLite, `PRAGMA foreign_keys` aislado en `db/engine.py`). El salto es:

1. **Motor**: `create_db_engine` acepta `postgresql+asyncpg` — la URL viene de `METATRACER_DATABASE_URL` (ya configurable). La app es single-writer así que **no requiere cambiar el orquestador**; solo se elimina el "un solo writer" como limitación física.
2. **Migraciones**: hoy `init_db` hace `create_all` + ALTER aditivo (postura sin Alembic). Para Postgres hay que **introducir Alembic** con una migración inicial desde el schema declarado (los modelos son la fuente de verdad; generarla con `alembic revision --autogenerate` en un entorno de dev).
3. **Vector**: cuando la tabla `finding` tenga millones de filas, el FTS5 local no escala. Opciones:
   - `pgvector` (`embedding vector(1536)` por finding, índice `ivfflat`), con un generador de embeddings **local y gratuito** (modelo small tipo `all-MiniLM-L6-v2` vía ONNX) — se cumple la regla de "APIs gratuitas".
   - El `KnowledgeRetriever` se reescribe detrás de la misma interfaz (`retrieve(payload) -> [RetrievedEvidence]`): **cero cambios** en el `AgentPipeline`.
4. **Concurrencia**: con Postgres ya no hace falta la limitación de "un scan a la vez" — pero es una **decisión de producto** no técnica: TASK-21/`_lock` del orquestador puede relajarse a `N runs concurrentes` con `asyncio.Semaphore`. Mantener la precaución: el LLM y el rate limit del dominio siguen siendo los recursos limitantes.

Esfuerzo estimado: alto (Alembic + asyncpg + recodificar retriever), pero **cada pieza está aislada** y fue diseñada para esto.

---

## 4. Eje C — Auth y multi-usuario

> **Estado 2026-09-18:** implementado como [TASK-24](../tasks/24-auth-basic.md). Cookie `HttpOnly` `SameSite=Lax` + CSRF double-submit (`X-CSRF-Token` vs cookie, `compare_digest`), roles `operator`/`viewer`, un usuario por instalación. Hash de contraseñas **stdlib** (`pbkdf2_hmac` SHA-256 600k, formato versionado `pbkdf2_sha256$…`) — cero dependencias nuevas (revisión supply-chain 2026-09-18: descarta bcrypt/argon2-cffi/passlib). Token de sesión persistido como SHA-256 (leak de BD ≠ cookies válidas), rotación en login, expiración validada en BD, provisionado fail-closed desde `METATRACER_AUTH_PASSWORD`. Kill-switch `METATRACER_AUTH_ENABLED` default `false` (v0.5.0 intacto); CLI sin login (postura documentada).

Precondición: una plataforma en red **no puede** seguir con "no authentication; bind to trusted network".

- **Modelo inicial (v3.0, no sobre-diseñar)**:
  - Sesión por cookie `HttpOnly` + CSRF token (sin OAuth/JWT todavía); contraseñas con `bcrypt`/`argon2` (nueva dependencia — revisión supply-chain).
  - Roles: `operator` (todo: crear scopes, lanzar scans, feedback) y `viewer` (solo lectura: dashboards, reportes, exports).
  - **Un usuario por instalación** (tabla `user` de una fila + contraseña del `.env`/primera ejecución) para la v3.0; multi-tenant con N usuarios se deja a v3.1.
- **Protección transversal**:
  - Los endpoints actuales (runs, scopes, webhooks, kb, feedback) ganan dependencias `Depends(get_current_user)` con el rol.
  - El foco: **webhooks y exports** son los más sensibles (pueden filtrar metadata de terceros). El payload webhook ya está sanitizado y con `PAYLOAD_KEYS` fijo.
  - El CLI (localhost, un solo operador) **sigue sin login** — la auth protege la superficie Web/API, no el CLI (postura documentada).
- **Sin oxigenar el threat model**: sigue prohibido subir severidad sin snippet, seguir redirects off-scope, o cualquier bypass. La auth no cambia las 7 reglas.

---

## 5. Cuadrante de prioridad (próximos 6–9 meses si seguimos aquí)

| | V (alto valor) | F (fácil) | Prioridad |
| :--- | :--- | :--- | :--- |
| Watch + delta | alta | media | **P0** — integra todo lo construido sin tocar el pipeline |
| Postgres + Alembic | alta | media-baja | P1 — desbloquea todo lo demás |
| pgvector (retriever real) | media | media | P1-bis — depende de Postgres |
| Auth básica (1 usuario) | alta | media | P2 — necesaria antes de exponer en red |
| CRON real + daemon systemd | media | alta | P2 — operar sin recargar |

## 6. Fuera de alcance (v3.0, deliberadamente)

- UI multi-tenant con espacios de trabajo compartidos.
- OAuth social / SSO / 2FA.
- Detección "activa" (auth scanning, login, fuzzing) — MetaTracer sigue siendo pasivo.
- Alta disponibilidad / clustering / cola de trabajos externa (Redis/ARQ) — se anota para cuando el volumen lo justifique con datos, no al adivinar.

---

## 7. Cómo se relaciona con el backlog existente

- No reemplaza: **extiende**. Todas las tasks TASK-00→21 siguen siendo válidas.
- TASK-15 (webhooks) es el punto de enganche del Eje A.
- TASK-14 (RAG) y el schema actual son el punto de enganche del Eje B.
- TASK-20 (UI polish) y TASK-21 (multi-engagement) son prerequisitos de pulido antes de exponer la plataforma.
- Cualquier implementación del Eje A/B/C requiere primero **revisión de seguridad formal** (reglas inviolables + threat model) y actualización de la lista cerrada de dependencias si se añade algo.