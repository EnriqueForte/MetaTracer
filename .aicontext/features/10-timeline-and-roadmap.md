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

v1.0–v1.2 están **cerradas**. La siguiente fase de producto es **v2.0 Plataforma**.

## Roadmap por fases

| Fase | Nombre | Principales entregables | Objetivo |
| --- | --- | --- | --- |
| v1.0 | MVP | Extracción PDF/imagen + detección de hallazgos + clasificación + reportes + agentes (LangGraph) + Web UI + CLI | **Cerrado 2026-09-06** (TASK-00→07 + validación real) |
| v1.1 | Usabilidad | Mejoras de CLI, exportación HTML, filtros, historial local, coherencia post-LLM | **Cerrada** — [TASK-08](../tasks/08-usability.md) |
| v1.2 | Expansión de fuentes | HTML, HTTP headers, comentarios JS | **Cerrada** — [TASK-09](../tasks/09-source-expansion.md) |
| v2.0 | Plataforma | Dashboard completo, gestión de scopes, notificaciones | Demostrar capacidad de producto — **Cerrada 2026-09-08** (TASK-10 scopes ✅, TASK-11 dashboard ✅, TASK-12 notificaciones ✅) |
| v2.1+ | Inteligencia avanzada | RAG, feedback loop, integraciones | Diferenciación fuerte en AI + OffSec — **en curso: TASK-13 feedback loop** |

## Mapeo a características del MVP

| Característica | Fase inicial |
| --- | --- |
| [Extracción de metadata](01-metadata-extraction.md) | v1.0 (PDF/imágenes); v1.2 (HTML/headers/JS) |
| [Detección específica](02-specific-detection.md) | v1.0 |
| [Clasificación de riesgo](03-risk-classification.md) | v1.0 |
| [Generación de reportes](04-report-generation.md) | v1.0; v1.1 exportación avanzada |
| [Agentes de IA](05-ai-agents.md) | v1.0; v2.1+ RAG y feedback |
| [Interfaces](06-interfaces.md) | v1.0 Web + CLI; v1.1 CLI/historial; v2.0 dashboard |
