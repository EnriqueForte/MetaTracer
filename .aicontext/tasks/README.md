# Backlog Técnico de Tareas a Bajo Nivel (Tasks)

**Proyecto:** MetaTracer  
**Versión:** 2.2 (Integraciones)  
**PRD:** [Volver al PRD](../PRD.md)  
**Estado:** MVP v1.0–v1.2 cerradas — v2.0 completada (TASK-10/11/12 ✅) — v2.1 completada (TASK-13 feedback ✅, TASK-14 RAG ligero ✅) — **v2.2 "Integraciones" completada 2026-09-13**: TASK-15 webhooks ✅, TASK-16 CI guardrail ✅, TASK-17 KB portable ✅, TASK-18 exports bounty ✅, TASK-19 import scope ✅ (todas cerradas; `pytest` 475 passed + ruff limpio + cobertura ≥85%) — **todas las fases del roadmap actual hasta v2.2 están cerradas**  

Este directorio descompone el MVP en tareas implementables. Cada archivo es un contrato: objetivo, subtareas, contratos de datos, fuera de alcance, tests mínimos y criterios de aceptación verificables.

Las features del PRD definen *qué* debe existir. Estas tasks definen *cómo* construirlo sin contradecir el PRD.

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
| `finding_type` | `gps` \| `email` \| `internal_path` \| `software_version` \| `debug_comment` |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `confidence` | `high` \| `medium` \| `low` |
| `detector_method` | `rule` \| `heuristic` \| `agent` |
| `reasoning_depth` | `brief` \| `standard` \| `detailed` (default: `standard`) |
| `run.status` | `pending` \| `running` \| `completed` \| `failed` \| `aborted` |
| `extraction_status` | `ok` \| `skipped` \| `failed` |
| `namespace` | `exif` \| `xmp` \| `pdfinfo` \| `iptc` \| `http` \| `html` \| `js` |
| Idioma de **reportes exportados** | Inglés (plataformas de bug bounty) |
| Idioma de **documentación** (esta carpeta) | Español |
| Idioma de **UI/CLI** | Inglés (audiencia internacional / portfolio) |

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
| **TASK-13** | [13-feedback-loop.md](13-feedback-loop.md) | Feedback loop: corrección humana persistida + few-shot memory (v2.1+) | TASK-00 a TASK-12 |
| **TASK-14** | [14-rag-lite.md](14-rag-lite.md) | RAG ligero: índice full-text FTS5 + contexto histórico al agente (v2.1+) | TASK-00 a TASK-13 |
| **TASK-15** | [15-webhooks.md](15-webhooks.md) | Webhooks de salida: config CRUD, dispatcher, relay buffer, run_ref (v2.2) | TASK-00 a TASK-14 |
| **TASK-16** | [16-ci-guardrail.md](16-ci-guardrail.md) | CI guardrail: GitHub Actions (PR rápido + main con e2e y cobertura), scripts locales, umbral coverage (v2.2) | TASK-00 a TASK-15 |
| **TASK-17** | [17-kb-portable.md](17-kb-portable.md) | KB portable: export/import JSON del corpus de precedentes, CLI `kb`, API (v2.2) | TASK-00 a TASK-16 |
| **TASK-18** | [18-exports-bounty.md](18-exports-bounty.md) | Exports bounty: exportador CSV + plantilla bounty en texto plano, `--format csv\|bounty`, API (v2.2) — **cerrada 2026-09-13** | TASK-00 a TASK-17 |
| **TASK-19** | [19-scope-import.md](19-scope-import.md) | Import scope: archivo JSON portable → CLI `scope import` + API `POST /api/scopes/import`, idempotente (v2.2) | TASK-00 a TASK-18 |

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

Si hay que recortar, proteger los [criterios de éxito](../features/09-success-criteria.md) antes que pulido de UI.

---

## Trampas conocidas (leer antes de implementar)

1. **Loopback vs tests:** `NetworkSafetyGuard` bloquea `127.0.0.1`. El servidor mock de fixtures de `TASK-07` necesita un bypass *opt-in* de test (`METATRACER_ALLOW_LOOPBACK=true`), nunca el default.
2. **HEAD no es universal:** algunos hosts no soportan `HEAD`. Fallback a `GET` con aborto por tamaño al primer chunk.
3. **Severity prematura:** si `TASK-02` rellena `severity=info`, los reportes mienten cuando el agente no corre. Dejar `null`.
4. **GPS Critical:** el heurístico no puede saber si unas coordenadas son “casa de un ejecutivo”. Tope heurístico de GPS = `high`.
5. **Producer genérico:** `Microsoft Word` sin versión **no** es finding. Se queda en metadata cruda.
6. **SQLite + async API:** un solo writer. Los scans de la API van en serie (lock por run), no en un pool de workers concurrentes en el MVP.
