# Timeline y roadmap

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Esfuerzo estimado

- **Disponibilidad:** ~12 horas/semana
- **Duración del MVP:** 10–14 semanas
- **Capacidad aproximada:** ~120–170 horas para v1.0

Si una fase se retrasa, proteger los [criterios de éxito](09-success-criteria.md) (hallazgos reales, reportes enviables, arquitectura explicable) antes que el pulido extra de UI.

## Slices sugeridos del MVP (v1.0)

El orden es orientativo; cada slice debe poder demostrarse.

| Semanas (aprox.) | Slice | Resultado |
| --- | --- | --- |
| 1–2 | Fundamentos | Layout del proyecto, SQLite, esqueleto Docker, hooks de scope/modo seguro |
| 3–5 | Extracción + detección | Ingesta PDF/imagen, cinco tipos de hallazgo, assets/findings persistidos |
| 6–8 | Agentes + clasificación | Grafo LangGraph, routing de modelos, explicaciones, límites de contexto |
| 9–11 | Reportes + UI + CLI | Reporte priorizado, export, ambas interfaces sobre un pipeline |
| 12–14 | Hardening | Dominios de prueba, docs, walkthrough de entrevista, rate limits |

**Estado del roadmap:** v1.0–v1.2 cerradas ✅ — v2.0 Plataforma cerrada ✅ — v2.1+ Inteligencia avanzada cerrada ✅ — **v2.2 Integraciones cerrada ✅ (2026-09-13, TASK-15→19, `pytest` 475 passed + ruff limpio)** — **v2.3 Performance & UI polish cerrada ✅ (2026-09-16)**: rate limit API + body cap (`test_api_performance.py` 6 passed) + pulido de UI y accesibilidad ([TASK-20](../tasks/20-ui-polish.md) — helpers `MetaTracerUI` compartidos, focus/ARIA/teclado, tests a11y) — **v2.4 Multi-engagement & paginación cerrada ✅ (2026-09-16)**: [TASK-21](../tasks/21-multi-engagement.md) — `scope_ids` (unión multi-scope → snapshot `allowed_scope`), paginación keyset de `/api/runs` (`next_cursor`/`has_more`/`total` global), wizard multi-scope y History con Older/Newer (`pytest` 528 passed + ruff limpio). **v3.0 Plataforma cerrada ✅ (2026-09-18)**: [TASK-22](../tasks/22-watch-headless.md) (Eje A — watch/headless: `metatracer watch` con deltas deterministas, lock por scope y `new_findings` en webhook), [TASK-23](../tasks/23-postgres-pgvector.md) (Eje B — PostgreSQL + asyncpg + Alembic + pgvector + `METATRACER_MAX_CONCURRENT_RUNS`), [TASK-24](../tasks/24-auth-basic.md) (Eje C — auth básica 1 usuario: cookie HttpOnly + CSRF + roles; `pytest` 603 passed + ruff limpio + cobertura ≥85%). **v3.1 planificada (2026-09-19)**: [TASK-25](../tasks/25-user-registration.md) (multi-usuario: first-run setup + panel admin + invitaciones) → [TASK-26](../tasks/26-ui-redesign.md) (rediseño de UI — **borrador, pendiente de redefinición del operador**).

## Roadmap por fases

| Fase | Nombre | Principales entregables | Objetivo |
| --- | --- | --- | --- |
| v1.0 | MVP | Extracción PDF/imagen + detección de hallazgos + clasificación + reportes + agentes (LangGraph) + Web UI + CLI | **Cerrado 2026-09-06** (TASK-00→07 + validación real) |
| v1.1 | Usabilidad | Mejoras de CLI, exportación HTML, filtros, historial local, coherencia post-LLM | **Cerrada** — [TASK-08](../tasks/08-usability.md) |
| v1.2 | Expansión de fuentes | HTML, HTTP headers, comentarios JS | **Cerrada** — [TASK-09](../tasks/09-source-expansion.md) |
| v2.0 | Plataforma | Dashboard completo, gestión de scopes, notificaciones | Demostrar capacidad de producto — **Cerrada 2026-09-08** (TASK-10 scopes ✅, TASK-11 dashboard ✅, TASK-12 notificaciones ✅) |
| v2.1+ | Inteligencia avanzada | RAG, feedback loop | **Cerrada** — TASK-13 feedback ✅, TASK-14 RAG ligero ✅ |
| v2.2 | Integraciones | Webhooks de salida + run_ref, KB portable, exports bounty, CI guardrail, import scope | **Cerrada 2026-09-13** (TASK-15 webhooks ✅, TASK-16 CI guardrail ✅, TASK-17 KB portable ✅, TASK-18 exports bounty ✅, TASK-19 import scope ✅ — `pytest` 475 passed + ruff limpio + cobertura ≥85%) |
| v2.3 | Performance & UI polish | Rate limit API + body cap (✅), pulido de UI: accesibilidad, empty states, consistencia de errores | **Cerrada 2026-09-16** — [TASK-20](../tasks/20-ui-polish.md) ✅ |
| v2.4 | Operación a escala | Multi-engagement (`scope_ids`), paginación por cursor del historial | **Cerrada 2026-09-16** — [TASK-21](../tasks/21-multi-engagement.md) ✅ |
| v3.0 | Plataforma | Watch/headless (Eje A) ✅, PostgreSQL+pgvector (Eje B) ✅, auth básica (Eje C) ✅ | **Cerrada 2026-09-18** — TASK-22 ✅, [TASK-23](../tasks/23-postgres-pgvector.md) ✅ (Eje B), [TASK-24](../tasks/24-auth-basic.md) ✅ (Eje C) — [12-platform-v3.md](12-platform-v3.md) |
| v3.1 | Multi-usuario & UI | Multi-usuario (first-run setup, panel admin, invitaciones) + rediseño de UI (design system propio, Tailwind compilado, sidebar) | **Planificada 2026-09-19** — [TASK-25](../tasks/25-user-registration.md) → [TASK-26](../tasks/26-ui-redesign.md) |

## Mapeo a características del MVP

| Característica | Fase inicial |
| --- | --- |
| [Extracción de metadata](01-metadata-extraction.md) | v1.0 (PDF/imágenes); v1.2 (HTML/headers/JS) |
| [Detección específica](02-specific-detection.md) | v1.0 |
| [Clasificación de riesgo](03-risk-classification.md) | v1.0 |
| [Generación de reportes](04-report-generation.md) | v1.0; v1.1 exportación avanzada |
| [Agentes de IA](05-ai-agents.md) | v1.0; v2.1+ RAG y feedback |
| [Interfaces](06-interfaces.md) | v1.0 Web + CLI; v1.1 CLI/historial; v2.0 dashboard |
