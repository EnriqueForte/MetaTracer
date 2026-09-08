# Requisitos no funcionales y decisiones técnicas

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Decisiones (validadas)

| Aspecto | Decisión | Por qué importa |
| --- | --- | --- |
| Lenguaje principal | Python | Ecosistema para parsers de metadata, agentes y scripting OffSec |
| Framework de agentes | LangGraph | Grafos explícitos que puedes explicar en una entrevista |
| Modelos | Kimi para trabajo complejo / desarrollo; modelos más baratos/rápidos para tareas simples | Control de coste + calidad donde cuenta |
| Base de datos | SQLite en el MVP; diseño preparado para PostgreSQL + pgvector después | MVP local sin ops; listo para vector/RAG más adelante |
| Despliegue | Local + Docker | Los hunters lo ejecutan en su máquina; demo reproducible |
| Optimización de contexto | Alta prioridad | Evitar saturar a los agentes; reducir alucinaciones |
| Coste | Herramientas/APIs gratuitas excepto Grok de pago | Mantener el proyecto ejecutable con presupuesto ajustado |

## Restricciones de arquitectura

- Mantener un límite claro: **ingestar/detectar (determinista) → agentes (interpretación) → reporte (presentación)**.
- La persistencia debe tratar **run**, **asset** y **finding** como registros separados: el historial de v1.1 ya se engancha ahí; RAG de v2.1+ podrá hacerlo después.
- No acoplar Web UI y CLI a pipelines distintos.
- Evitar meter binarios o dumps completos de archivos (ni HTML/JS) en el contexto del LLM. Detalle: [agentes de IA](05-ai-agents.md).
- v1.2 amplió namespaces (`http` / `html` / `js`) sobre el mismo modelo `Asset` + `RawMetadataItem`; no hay un segundo pipeline.

## Atributos de calidad

| Atributo | Expectativa del MVP |
| --- | --- |
| Safety | Check de scope + rate limit + modo seguro por defecto. [Ética](08-ethics-legal-safety.md) |
| Fiabilidad | Un asset fallido no tumba el run |
| Observabilidad | Guardar status, errores, ids de modelo/run junto a los hallazgos |
| Explicabilidad | Arquitectura y grafo listos para entrevista. [Criterios de éxito](09-success-criteria.md) |
| Portabilidad | La imagen Docker ejecuta el mismo flujo que Python local |
| Coste | Preferir APIs gratuitas; enrutar trabajo simple a modelos baratos |

## Postura de migración (no en el MVP)

SQLite ahora. El schema y la capa de acceso no deben bloquear un paso posterior a PostgreSQL + pgvector (necesario para [RAG en v2.1+](10-timeline-and-roadmap.md)).

## Relación con características

- Agentes y modelos → [Agentes de IA](05-ai-agents.md)
- Despliegue local + Docker → [Interfaces](06-interfaces.md)
- Datos producidos por → [Extracción de metadata](01-metadata-extraction.md) y [Detección específica](02-specific-detection.md)
