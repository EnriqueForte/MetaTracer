# Backlog Técnico de Tareas a Bajo Nivel (Tasks)

**Proyecto:** MetaTracer  
**Versión:** 3.2 cerrada (hardening post-auditoría 2026-10-03, TASK-27 → TASK-35, 2026-10-05) — suite verificada 2026-10-23  
**PRD:** [Volver al PRD](../PRD.md)  
**Estado:** MVP **v1.0–v1.2 cerradas** (TASK-00 → TASK-09) — **v2.0 completada** (TASK-10/11/12 ✅) — **v2.1 completada** (TASK-13 feedback ✅, TASK-14 RAG ligero ✅) — **v2.2 "Integraciones" completada 2026-09-13** (TASK-15 a TASK-19 ✅; 475 passed + ruff limpio + cobertura ≥85%) — **v2.3 "Performance & UI polish" cerrada 2026-09-16** (TASK-20 ✅; 528 passed) — **v2.4 "Multi-engagement" cerrada 2026-09-16** (TASK-21 ✅). **Plataforma v3.0 cerrada**: [visión](../features/12-platform-v3.md) — **TASK-22 (Eje A, watch/headless) 2026-09-16** (`metatracer watch` con `--once`/`--interval`/`--webhook`, lock por scope, `DeltaReporter` determinista sin LLM, `new_findings` en el webhook) · **TASK-23 (Eje B, PostgreSQL + pgvector) 2026-09-17** (`postgresql+asyncpg` exigido, migraciones Alembic empaquetadas y ejecutadas en `init_db`, `PgVectorKnowledgeIndex` con hashing-trick 384-d tras la misma interfaz `KnowledgeRetriever`, `METATRACER_MAX_CONCURRENT_RUNS`, compose profile `postgres` con `pgvector/pgvector:pg17`) · **TASK-24 (Eje C, auth básica) 2026-09-18** (cookie `HttpOnly` + CSRF double-submit, roles `operator`/`viewer`, **PBKDF2-SHA256 600k stdlib** versionado, token de sesión solo-hash, rotación en login, kill-switch `METATRACER_AUTH_ENABLED`, CLI sin login; suite **598 passed**, cobertura 87.2%). **v3.1 cerrada 2026-09-21**: [TASK-25](25-user-registration.md) multi-usuario (first-run setup, panel de admin, invitaciones de un solo uso, registro desde Sign In) → [TASK-26](26-ui-redesign.md) rediseño de la Web UI (design system `.mt-*`; entrega V1 histórica, sustituida por Web V2). **v3.2 cerrada 2026-10-05**: [TASK-27](27-security-hardening-p0.md) → [TASK-35](35-ui-ux-improvements.md) — ver la tabla de mapeo abajo. **Suite verificada 2026-10-23: 787 passed, 6 skipped** (e2e incluido) · **cobertura 91.30%** (DoD ≥85%) · ruff limpio. Tests Postgres se skipean sin servidor (el redir local de Docker Desktop no cuenta como servidor).

Este directorio descompone el MVP en tareas implementables. Cada archivo es un contrato: objetivo, subtareas, contratos de datos, fuera de alcance, tests mínimos y criterios de aceptación verificables.

Las features del PRD definen *qué* debe existir. Estas tasks definen *cómo* construirlo sin contradecir el PRD.

> **Gobernanza (2026-11-19):** TASK-00–35 y specs 36–53 están **closed**.
> Spec 54 **active**: host público del lab (no producto). Spec **55 closed**: grafos en vivo del scan.
> Spec **56 closed**: instalador y lanzador Windows + Linux/Parrot. No mover TASK-00–53 a `archive/`.

---

## Cómo ejecutar este backlog

1. Implementar **en orden numérico** (`TASK-00` → `TASK-07`). Las dependencias no son opcionales.
2. Cumplir el DoD de una task (incluidos sus tests mínimos) **antes** de abrir la siguiente.
3. Los tests se escriben **en la misma slice** que el código. `TASK-07` no es el momento de empezar a testear: consolida e2e, fixtures y Docker.
4. Si una decisión no está en la task ni en la feature, elegir la opción más simple que respete las [reglas inviolables](#reglas-inviolables) y documentarla en código (docstring o comentario breve).
5. No adelantar trabajo de slices posteriores (p. ej. no montar React en `TASK-00`, no llamar al LLM en `TASK-02`).

---

## Contratos compartidos (fuente de verdad)

Valores **en minúsculas** en base de datos, JSON, API y Pydantic. La capa de presentación (CLI/UI/Markdown) puede mostrarlos en Title Case (`High`, `Critical`).

| Contrato | Valores |
| :--- | :--- |
| `finding_type` | `gps` \| `email` \| `internal_path` \| `software_version` \| `debug_comment` \| `internal_endpoint` \| `cloud_storage` \| `secret` ([TASK-37](37-new-detectors.md): `internal_endpoint` = IPv4 RFC1918 o hostname `.internal`/`.corp`/`.local`/`.lan`/`*.svc.cluster.local`, techo `medium`. `cloud_storage` = host S3/GCS/Azure Blob/R2, techo `high`; el producto no pide esa URL. [TASK-49](49-secret-finding.md): `secret` = allowlist cerrada AKIA / `ghp_` / PEM / JWT compact en valores ya extraídos, techo `critical`. Ninguno es `author_name`) |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `confidence` | `high` \| `medium` \| `low` |
| `detector_method` | `rule` \| `heuristic` \| `agent` |
| `reasoning_depth` | `brief` \| `standard` \| `detailed` (default: `standard`) |
| `run.status` | `pending` \| `running` \| `completed` \| `failed` \| `aborted` |
| `extraction_status` | `ok` \| `skipped` \| `failed` |
| `skip_reason` | `unsupported_type` \| `too_large` \| `out_of_scope` \| `duplicate_hash` \| `empty_body` \| `robots_disallow` (`robots_disallow` es cortesía de `robots.txt`: la URL no se solicita; no autoriza hosts, no es una decisión de scope y no prueba que el recurso no exista) |
| `namespace` | `exif` \| `xmp` \| `pdfinfo` \| `iptc` \| `http` \| `html` \| `js` \| `ooxml` \| `odf` ([TASK-37](37-new-detectors.md): `ooxml`/`odf` = propiedades del paquete, nunca el cuerpo del documento) |
| límites de crawl (Fase 2) | `max_depth` \| `max_pages` \| `max_assets` \| `max_total_bytes` \| `max_seconds` (se registran en `Run.ingestion_stats.limits_hit`; identificadores estables, no traducir) |
| `user.role` (TASK-24) | `operator` \| `viewer` |
| `triage_status` (TASK-35) | `open` \| `confirmed` \| `false_positive` \| `fixed` (default: `open`; solo lo cambia un operador, nunca el agente; independiente de `severity`; `false_positive` queda fuera de exports y conteos salvo inclusión explícita) |
| `investigation.status` (Fase 3, [TASK-36](36-investigations.md)) | `open` \| `closed` (agrupa runs; no aísla clientes: una instalación sigue siendo un solo dominio de confianza. El triaje de otro run del mismo grupo se *sugiere*, nunca se copia solo) |
| `correlation.kind` (Fase 3, TASK-36) | `email` \| `gps_point` \| `internal_endpoint` \| `software_version` \| `document_id` \| `device_serial` \| `author_string` (dos assets que comparten `value_hash` comparten un valor, no una identidad. `internal_endpoint` lo escribe el detector homónimo, TASK-37. `author_string` no es un hallazgo: ADR-0009 sigue en pie) |
| `connector.status` (Fase 4, [TASK-38](38-connectors.md)) | `disabled` \| `available` \| `degraded` \| `error` (apagado = ninguna petición; `degraded` es un 429 y no tumba un run) |
| `export.redaction` (Fase 5, [TASK-39](39-export-redaction.md)) | `none` \| `contacts` \| `coordinates` \| `all` (solo el fichero exportado; la base no cambia. API y CLI por defecto `none`. La UI de descarga propone `contacts`) |
| `normalized_kind` | `decimal_degrees` \| `iso8601_utc` \| `lowercase_trim` (el `value` original no se sobrescribe; NULL si no hay forma normalizada distinta) |
| `timezone_status` | `known` \| `assumed_utc` \| `unzoned` \| `invalid` (NULL si el campo no es una fecha) |
| `graph_node.kind` ([TASK-55](55-scan-live-graph.md)) | `page` \| `asset` \| `local_root` \| `value` (nodo de grafo de scan; `value` es un `value_norm` de correlación, no una identidad) |
| `discovery_edge.kind` ([TASK-55](55-scan-live-graph.md)) | `page` \| `document` \| `script` \| `probe` \| `local` (arista persistida de descubrimiento; `local` = estrella `file:` raíz → fichero) |
| Idioma de **reportes exportados** | Inglés (plataformas de bug bounty) |
| Idioma de **documentación** (esta carpeta) | Español |
| Idioma de **Web UI** (`web/`) | Español |
| Idioma de **CLI** | Inglés |

`severity` en un `Finding` es **nullable** hasta que corre el clasificador (heurístico o agente). Los detectores **nunca** asignan severidad.

---

## Reglas inviolables

Aplican a **todas** las tasks. Un PR que las viole no está done.

- No hay red sin `scope_confirmed=True` y sin pasar `ScopeValidator` + `NetworkSafetyGuard`.
- No hay modo oculto que desactive el safety en la distribución por defecto.
- Nunca persistir bytes de archivos ni enviarlos al LLM. Solo metadata estructurada y snippets cortos.
- Nunca seguir redirects fuera de scope.
- Un asset fallido no tumba el run.
- Los agentes no inventan evidencia, no cambian `finding_type` ni `evidence_snippet`, y no generan exploits/payloads.
- El clasificador heurístico no hace OSINT, geocoding ni lookup de CVEs.
- Loopback/IPs privadas están bloqueadas en runtime normal. El bypass es **solo** para tests, por variable de entorno, nunca activo por defecto.

---

## Estructura y mapeo de tareas

| Código | Archivo | Módulo | Dependencias |
| :--- | :--- | :--- | :--- |
| **TASK-00** | [00-architecture-and-safety.md](00-architecture-and-safety.md) | Layout, config, SQLite, Safety Core | Ninguna |
| **TASK-01** | [01-metadata-extraction.md](01-metadata-extraction.md) | Ingesta, crawler, extractores PDF/imagen | TASK-00 |
| **TASK-02** | [02-specific-detection.md](02-specific-detection.md) | 5 detectores + deduplicación | TASK-00, TASK-01 |
| **TASK-03** | [03-risk-classification.md](03-risk-classification.md) | Rúbrica + clasificador heurístico | TASK-00, TASK-02 |
| **TASK-04** | [04-report-generation.md](04-report-generation.md) | Reportes Markdown/JSON | TASK-02, TASK-03 |
| **TASK-05** | [05-ai-agents.md](05-ai-agents.md) | LangGraph, sanitizer, fallback | TASK-02, TASK-03 |
| **TASK-06** | [06-interfaces.md](06-interfaces.md) | Orquestador, CLI, API, Web UI | TASK-00 a TASK-05 |
| **TASK-07** | [07-testing-and-deployment.md](07-testing-and-deployment.md) | Fixtures, e2e, Docker | Todas |
| **TASK-08** | [08-usability.md](08-usability.md) | Historial, filtros, export HTML, CLI show, guard de coherencia | TASK-00 a TASK-07 |
| **TASK-09** | [09-source-expansion.md](09-source-expansion.md) | HTML, cabeceras HTTP, comentarios JS como fuentes | TASK-00 a TASK-08 |
| **TASK-10** | [10-scope-management.md](10-scope-management.md) | Scopes persistentes, CRUD API, select en wizard (v2.0) | TASK-00 a TASK-09 |
| **TASK-11** | [11-dashboard.md](11-dashboard.md) | Dashboard agregado + GET /api/stats (v2.0) | TASK-00 a TASK-10 |
| **TASK-12** | [12-notifications.md](12-notifications.md) | Notificaciones: cola en memoria, campana en la UI, `GET/DELETE /api/notifications` (v2.0) — cerrada | TASK-00 a TASK-11 |
| **TASK-13** | [13-feedback-loop.md](13-feedback-loop.md) | Feedback loop: corrección humana persistida + few-shot memory (v2.1+) | TASK-00 a TASK-12 |
| **TASK-14** | [14-rag-lite.md](14-rag-lite.md) | RAG ligero: índice full-text FTS5 + contexto histórico al agente (v2.1+) | TASK-00 a TASK-13 |
| **TASK-15** | [15-webhooks.md](15-webhooks.md) | Webhooks de salida: config CRUD, dispatcher, relay buffer, run_ref (v2.2) | TASK-00 a TASK-14 |
| **TASK-16** | [16-ci-guardrail.md](16-ci-guardrail.md) | CI guardrail: GitHub Actions (PR rápido + main con e2e y cobertura), scripts locales, umbral coverage (v2.2) | TASK-00 a TASK-15 |
| **TASK-17** | [17-kb-portable.md](17-kb-portable.md) | KB portable: export/import JSON del corpus de precedentes, CLI `kb`, API (v2.2) | TASK-00 a TASK-16 |
| **TASK-18** | [18-exports-bounty.md](18-exports-bounty.md) | Exports bounty: exportador CSV + plantilla bounty en texto plano, `--format csv\|bounty`, API (v2.2) — **cerrada 2026-09-13** | TASK-00 a TASK-17 |
| **TASK-19** | [19-scope-import.md](19-scope-import.md) | Import scope: archivo JSON portable → CLI `scope import` + API `POST /api/scopes/import`, idempotente (v2.2) | TASK-00 a TASK-18 |
| **TASK-20** | [20-ui-polish.md](20-ui-polish.md) | UI polish y accesibilidad: matriz de estados por página, `readError`/Retry compartidos, focus/ARIA/teclado, tests a11y (v2.3) — **cerrada 2026-09-16** | TASK-00 a TASK-19 |
| **TASK-21** | [21-multi-engagement.md](21-multi-engagement.md) | Multi-engagement: unión de varios scopes guardados por run (`scope_ids`) + paginación por cursor del historial (v2.4) — **cerrada 2026-09-16** | TASK-00 a TASK-20 |
| **TASK-22** | [22-watch-headless.md](22-watch-headless.md) | Watch/headless: `metatracer watch` con `--once`/`--interval`/`--webhook`, lock por scope, delta determinista sin LLM y `new_findings` en webhook (v3.0, Eje A) — **cerrada 2026-09-16** | TASK-00 a TASK-21 |
| **TASK-23** | [23-postgres-pgvector.md](23-postgres-pgvector.md) | Eje B: PostgreSQL + asyncpg + Alembic + índice pgvector + `METATRACER_MAX_CONCURRENT_RUNS` (v3.0) — **cerrada 2026-09-17** | TASK-00 a TASK-22 |
| **TASK-24** | [24-auth-basic.md](24-auth-basic.md) | Eje C: auth básica 1 usuario — cookie `HttpOnly` + CSRF, roles `operator`/`viewer`, PBKDF2 stdlib, kill-switch `METATRACER_AUTH_ENABLED` (v3.0) — **cerrada 2026-09-18** | TASK-00 a TASK-23 |
| **TASK-25** | [25-user-registration.md](25-user-registration.md) | Multi-usuario v3.1: first-run setup desde la UI, panel de admin de usuarios, invitaciones de un solo uso y registro desde Sign In — **cerrada 2026-09-21** | TASK-00 a TASK-24 |
| **TASK-26** | [26-ui-redesign.md](26-ui-redesign.md) | Rediseño visual de la Web UI — **cerrada 2026-09-21** (contrato original: tokens `.mt-*`, Tailwind offline). **Histórico:** esa entrega era Web V1 (Alpine en `/static`); T11/ADR-0016 retiró V1. Contrato visual vigente: `.aicontext/ui/design-system-v2.md` | TASK-00 a TASK-25 |
| **TASK-27** | [27-security-hardening-p0.md](27-security-hardening-p0.md) | v3.2 P0: `trust_env=False`, auth obligatoria en bind público, HMAC real en webhooks, CSV anti-fórmula, tope pre-inflate de XMP — **cerrada 2026-10-03** | TASK-00 a TASK-26 |
| **TASK-28** | [28-run-recovery-abort.md](28-run-recovery-abort.md) | v3.2 P1: recovery de runs huérfanos al arrancar + abort cooperativo (API, CLI, Web V2) — **cerrada 2026-10-03** | TASK-27 |
| **TASK-29** | [29-agent-output-integrity.md](29-agent-output-integrity.md) | v3.2 P1: techo del guard respeta el feedback, guard de prosa LLM, escape en Markdown — **cerrada 2026-10-03** | TASK-27 |
| **TASK-30** | [30-data-retention.md](30-data-retention.md) | v3.2 P1: borrado de runs sin huérfanos + retención configurable (GDPR) — **cerrada 2026-10-03** | TASK-28 |
| **TASK-31** | [31-api-authz-hardening.md](31-api-authz-hardening.md) | v3.2 P1: tope de body con chunked + lecturas admin solo operator — **cerrada 2026-10-03** | TASK-27 |
| **TASK-32** | [32-core-hygiene.md](32-core-hygiene.md) | v3.2 P2: kill-switch de loopback, rangos IP, IDN, rate limiter, extractores, lockfile — **cerrada 2026-10-05** | TASK-27 |
| **TASK-33** | [33-backend-hygiene.md](33-backend-hygiene.md) | v3.2 P2: SSE tras evicción, retries de webhook, índices/N+1, lockout de login, import circular, `/api/ready` — **cerrada 2026-10-05** | TASK-28, TASK-31 |
| **TASK-34** | [34-detector-precision.md](34-detector-precision.md) | v3.2 P2: falsos positivos de email/GPS/secretos, rutas, presupuesto y caché del agente — **cerrada 2026-10-03** | TASK-29 |
| **TASK-35** | [35-ui-ux-improvements.md](35-ui-ux-improvements.md) | v3.2 UI/UX Web V2: arreglos de triage y paridad, cambios sin commit, filtros en URL, paleta y atajos, mapa GPS, tendencias, comparación de runs, abort/delete, pantallas Webhooks/Knowledge, TanStack Query + Zod, triage de findings (`false_positive`), light mode — **cerrada 2026-10-05** | TASK-26 (35.5: TASK-28, TASK-30) |
| **TASK-36** | [36-investigations.md](36-investigations.md) | Fase 3: investigations + correlación; paridad CLI `investigation` + contrato SDD — **cerrada 2026-11-05** | TASK-35 |
| **TASK-37** | [37-new-detectors.md](37-new-detectors.md) | Detectores `internal_endpoint`/`cloud_storage` + extractores OOXML/ODF — **cerrada 2026-11-05** | TASK-02, TASK-03, v3.2 |
| **TASK-38** | [38-connectors.md](38-connectors.md) | Conectores de egreso (RDAP/Wayback/CC) — **cerrada 2026-11-05** | TASK-15 |
| **TASK-39** | [39-export-redaction.md](39-export-redaction.md) | Redacción de exports (`export.redaction`) — **cerrada 2026-11-05** | TASK-04, TASK-18 |
| **TASK-41** | [41-ops-hygiene.md](41-ops-hygiene.md) | Lock durable, resume abort, métricas, `/api/v1` — **cerrada 2026-11-05** | TASK-28, TASK-33 |
| **TASK-43** | [43-ui-investigations.md](43-ui-investigations.md) | UI de investigations: listado y ficha en Web V2 — **cerrada 2026-11-05** | TASK-36 |
| **TASK-49** | [49-secret-finding.md](49-secret-finding.md) | `finding_type: secret` (allowlist AKIA/`ghp_`/PEM/JWT) — **cerrada 2026-11-13** | TASK-02, TASK-03, TASK-05 |
| **TASK-50** | [50-watch-deltas.md](50-watch-deltas.md) | Watch `resolved_findings` / `severity_up_count` en `PAYLOAD_KEYS` — **cerrada 2026-11-13** | TASK-22, TASK-44 |
| **TASK-51** | [51-local-ingest.md](51-local-ingest.md) | Ingesta local de carpeta (cero red, mismos extractores) — **cerrada 2026-11-13** | TASK-01, TASK-09 |
| **TASK-56** | [56-clone-install.md](56-clone-install.md) | Instalador y lanzador post-clone (Windows + Linux/Parrot) — **cerrada 2026-11-19** | T11, TASK-07 |

`TASK-04` **no** depende de `TASK-05`: el motor de reportes debe funcionar con clasificaciones heurísticas (campos de explicación vacíos o plantilla). `TASK-05` rellena justificación, impacto, remediación y repro. `TASK-06` orquesta el pipeline completo.

---

## Flujo del pipeline

La UI/CLI son el **punto de entrada y de presentación**, no una etapa de datos al final.

```text
 CLI / Web UI  (TASK-06)
        │
        ▼
 Safety Gate   (TASK-00)     rechaza fuera de scope / IP privada / scope no confirmado
        │
        ▼
 Ingest + Extract (TASK-01+09)  rate-limit → PDF / EXIF / HTML / HTTP / JS → RawMetadataItem
        │
        ▼
 Detectors     (TASK-02)     5 tipos → Finding (severity = null)
        │
        ▼
 Classify      (TASK-03)     heurístico siempre disponible
        │
        ▼
 Agents        (TASK-05)     opcional; si falla → fallback a TASK-03
        │
        ▼
 Reports       (TASK-04+08)  Markdown + JSON + HTML en inglés, ordered Critical→Info
        │
        ▼
 CLI / Web UI  (TASK-06)     misma fuente de datos, mismos hallazgos
```

`TASK-07` no está en el flujo de runtime: cubre fixtures, tests e2e y contenedor.

---

## Fases y slices

Alineado con [Timeline y roadmap](../features/10-timeline-and-roadmap.md).

| Slice | Semanas | Tasks | Resultado demostrable |
| :--- | :--- | :--- | :--- |
| 1 | 1–2 | `TASK-00` | Proyecto instalable, SQLite, safety que bloquea de verdad |
| 2 | 3–5 | `TASK-01`, `TASK-02` | De URL/dominio a findings persistidos (sin LLM) |
| 3 | 6–8 | `TASK-03`, `TASK-05` | Severidad justificada + explicaciones + fallback |
| 4 | 9–11 | `TASK-04`, `TASK-06` | Reporte enviable + CLI + Web UI sobre el mismo servicio |
| 5 | 12–14 | `TASK-07` | Fixtures, e2e verde, Docker, walkthrough |
| 6 | post-MVP | `TASK-08` | Historial local, filtros, export HTML, CLI usable día a día |
| 7 | v1.2 | `TASK-09` | HTML, cabeceras HTTP y comentarios JS como findings |
| 8 | v2.0 | `TASK-10` | Scopes persistentes + CRUD + select en el wizard |
| 9 | v2.0 | `TASK-11` | Dashboard agregado + `/api/stats` |
| 10 | v2.0 | `TASK-12` | Notificaciones: cola en memoria, campana en la UI, `GET/DELETE /api/notifications` |
| 11 | v2.1+ | `TASK-13` | Feedback loop: corrección persistida + few-shot memory en clasificación/agente |
| 12 | v2.1+ | `TASK-14` | RAG ligero: índice FTS5 + contexto histórico recuperado para el agente |
| 13 | v2.2 | `TASK-15` | Webhooks de salida + `run_ref`: relay buffer, retries/backoff, anti-SSRF en egreso |
| 14 | v2.2 | `TASK-16` | CI guardrail: GitHub Actions + scripts locales + cobertura ≥85% |
| 15 | v2.2 | `TASK-17` | KB portable: JSON export/import del corpus RAG + CLI `kb` + API |
| 16 | v2.2 | `TASK-18` | Exports bounty: exportador CSV + plantilla bounty en texto plano + `--format csv\|bounty` + API |
| 17 | v2.2 | `TASK-19` | Import scope: archivo JSON portable → CLI `scope import` + API `POST /api/scopes/import` (idempotente) |
| 18 | v2.3 | `TASK-20` | UI polish y accesibilidad: estados consistentes, `readError`/Retry únicos, focus/ARIA/teclado, tests a11y — **cerrada 2026-09-16** |
| 19 | v2.4 | `TASK-21` | Multi-engagement: unión de scopes por run + paginación por cursor del historial — **cerrada 2026-09-16** |
| 20 | v3.0 | `TASK-22` | Watch/headless (Eje A): `metatracer watch` con deltas deterministas y `new_findings` en webhook — **cerrada 2026-09-16** |
| 21 | v3.0 | `TASK-23` | Eje B: PostgreSQL + asyncpg + Alembic + pgvector + concurrencia acotada — **cerrada 2026-09-17** |
| 22 | v3.0 | `TASK-24` | Eje C: auth básica 1 usuario (cookie + CSRF + roles) — **cerrada 2026-09-18** |
| 23 | v3.1 | `TASK-25` | Multi-usuario: first-run setup + panel admin + invitaciones + registro en Sign In — **cerrada 2026-09-21** |
| 24 | v3.1 | `TASK-26` | Rediseño visual de la Web UI — **cerrada 2026-09-21** (V1 histórica; UI vigente = Web V2 en `web/`) |
| 25 | v3.2 | `TASK-27` → `TASK-35` | Hardening post-[auditoría 2026-10-03](../audit-2026-10-03.md): P0 seguridad, recovery/abort, integridad del agente, retención, authz del API, higiene de core/backend, precisión de detectores y mejoras UI/UX de la Web V2 — **cerrada 2026-10-05**. Orden ejecutado: 27 → 28 → 31 → 29 → 30 → 34 → 32 → 33; TASK-35 en paralelo (35.1–35.3 sin dependencias de backend) |
| 26 | v3.3 | `TASK-36` | Investigations + correlación: contrato SDD y CLI `metatracer investigation` (backend/API ya existían) |
| 27 | v3.3 | `TASK-43` | UI de investigations: `/investigations` y ficha de grupo en Web V2 |

Si hay que recortar, proteger los [criterios de éxito](../features/09-success-criteria.md) antes que pulido de UI.

---

## Trampas conocidas (leer antes de implementar)

1. **Loopback vs tests:** `NetworkSafetyGuard` bloquea `127.0.0.1`. El servidor mock de fixtures de `TASK-07` necesita un bypass *opt-in* de test (`METATRACER_ALLOW_LOOPBACK=true`), nunca el default.
2. **HEAD no es universal:** algunos hosts no soportan `HEAD`. Fallback a `GET` con aborto por tamaño al primer chunk.
3. **Severity prematura:** si `TASK-02` rellena `severity=info`, los reportes mienten cuando el agente no corre. Dejar `null`.
4. **GPS Critical:** el heurístico no puede saber si unas coordenadas son “casa de un ejecutivo”. Tope heurístico de GPS = `high`.
5. **Producer genérico:** `Microsoft Word` sin versión **no** es finding. Se queda en metadata cruda.
6. **SQLite + async API:** un solo writer. Los scans de la API van en serie (lock por run), no en un pool de workers concurrentes en el MVP.
7. **Multi-scope (TASK-21):** la unión de scopes guardados se resuelve en el orquestador y se copia a `Run.allowed_scope` (snapshot, TASK-10). El `ScopeValidator` usa la unión: el matching no cambia. Nunca mezclar `scope_domains` con `scope_ids` en un mismo request.
