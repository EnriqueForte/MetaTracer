# Spec 00 — Gobernanza SDD

**Estado:** closed  
**Agente:** `docs-architect`  
**Skill:** `metatracer-sdd`  
**Código de producto:** ninguno (`src/` y `web/` salvo prefijo de `web/AGENTS.md`)

## Intención

Dar a los agentes una memoria de trabajo, un overlay de specs activas y un ritual para que
los enums de Fase 3–5 no se implementen por accidente. Alinear `AGENTS.md`, catálogos,
skills de plataforma/SDD y prompts de agentes con T11/T12 (Web V2, FastAPI solo-API).

## Entregables

- `MEMORY.md`
- `specs/` (README, current, backlog, esta spec, 36–43 reserved)
- Banners en `.aicontext/PRD.md`, `features/10-timeline-and-roadmap.md`, `tasks/README.md`
- Skills `metatracer-sdd` y `metatracer-platform`
- Catálogos `.agents/agents.md` y `.agents/skills.md`
- Prompts: `docs-architect`, `ui-architect` (V2 corto), `ui-engineer` (CLI+API)
- Prefijo de producto en `web/AGENTS.md`

## Fuera de alcance

Implementar investigations, detectores nuevos, ONNX, conectores, redacción, higiene ops, UI de producto. Tercera rule always-on de SDD (se prefiere skill). Mover TASK-00–35 a `archive/`.

## DoD

- [x] Overlay y MEMORY existen; backlog refleja prioridades 36–43 (sin watch-cron).
- [x] Fase 3–5 etiquetadas reserved en `tasks/README.md`.
- [x] Agentes/catálogos no contradicen T11/T12.
- [x] Diff sin `src/` ni cambios de UI de producto (salvo `web/AGENTS.md`).
