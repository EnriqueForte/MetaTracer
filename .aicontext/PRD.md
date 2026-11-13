# Product Requirements Document (PRD)

**Nombre del proyecto:** MetaTracer  
**Versión del documento:** 0.3  
**Fecha:** 6 de septiembre de 2026  
**Autor:** Enrique Forte  
**Estado:** histórico de producto hasta v3.2. **Trabajo activo:** [`MEMORY.md`](../MEMORY.md) y [`specs/`](../specs/README.md).  

Índice del PRD. Cada archivo es una especificación: alcance, requisitos y criterios de aceptación donde aplica.

> **v3.2 cerrado** (2026-10-05). Dashboard, Web V2 en origen, auth y watch `--interval` ya existen.
> Specs 36–52 closed. Overlay v3.4 sin reserved. Código de producto exige spec
> `active` + TASK-NN. `secret` es `finding_type` (TASK-49).

**Nota de convención:** los nombres de archivo y la carpeta `features/` se mantienen en **inglés**; el contenido de la documentación está en **español**. Los enlaces apuntan a las mismas rutas, así que no hay descuadre entre el índice y los specs.

**Posicionamiento:** AI-powered sensitive metadata discovery for Bug Bounty & Red Team.

## Visión y contexto

- [Visión del producto](features/product-vision.md)
- [Usuarios objetivo](features/target-users.md)
- [Flujo de usuario (MVP)](features/user-flow.md)

## Características del MVP (v1.0)

| # | Característica | Archivo |
| --- | --- | --- |
| 1 | Extracción de metadata | [01-metadata-extraction.md](features/01-metadata-extraction.md) |
| 2 | Detección específica | [02-specific-detection.md](features/02-specific-detection.md) |
| 3 | Clasificación de riesgo | [03-risk-classification.md](features/03-risk-classification.md) |
| 4 | Generación de reportes | [04-report-generation.md](features/04-report-generation.md) |
| 5 | Agentes de IA | [05-ai-agents.md](features/05-ai-agents.md) |
| 6 | Interfaces (Web UI + CLI) | [06-interfaces.md](features/06-interfaces.md) |

**Fuentes:** v1.0 documentos públicos (PDFs e imágenes). v1.2 añade HTML, cabeceras HTTP y comentarios JS. El dashboard de plataforma se entregó en v2.0 (TASK-11).

## Post-MVP

| Fase | Archivo |
| :--- | :--- |
| v1.1 Usabilidad | [TASK-08](tasks/08-usability.md) — historial local, filtros, export HTML, CLI `show` (cerrada) |
| v1.2 Expansión de fuentes | [TASK-09](tasks/09-source-expansion.md) — HTML, cabeceras HTTP, comentarios JS (cerrada) |

## Transversal

- [Requisitos no funcionales y decisiones técnicas](features/07-technical-requirements.md)
- [Ética, legal y safety](features/08-ethics-legal-safety.md)
- [Criterios de éxito](features/09-success-criteria.md)
- [Timeline y roadmap](features/10-timeline-and-roadmap.md)
- [Walkthrough (10 minutos)](walkthrough.md)
- [Decisiones de arquitectura (ADRs)](decisions/)
- [Referencias e inspiración](features/11-references.md)

## Backlog Técnico de Tareas

- [Desglose de tareas a bajo nivel (Tasks Backlog)](tasks/README.md) — TASK-00–35 cerradas
- [Specs activas / reserved](../specs/README.md) — v3.4 (46–51 closed)

