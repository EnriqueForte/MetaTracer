---
name: metatracer-sdd
description: Ritual Spec-Driven Development de MetaTracer — MEMORY.md, specs/ (reserved/active/closed), tasks, skills y cierre. Usar al escribir o cambiar specs/, MEMORY.md, .aicontext/tasks/, o al abrir una slice TASK-36+.
---

# Spec-Driven Development

Índice: [`specs/README.md`](../../../specs/README.md). Memoria: [`MEMORY.md`](../../../MEMORY.md).
Catálogo: [`.agents/skills.md`](../../../.agents/skills.md).

## Qué capa es cada cosa

| Capa | Dónde | Hace |
| :--- | :--- | :--- |
| Memoria de trabajo | `MEMORY.md` | Estado, prohibiciones, cierre reciente |
| Intención | `specs/NN-*.md` | Alcance, OOS, dueño, estado |
| Enums | `.aicontext/tasks/README.md` + rule `data-contracts` | Valores cerrados |
| Implementación | `.aicontext/tasks/NN-*.md` | Subtareas, tests, DoD |
| Dominio JIT | `.cursor/skills/` | Al **abrir** la slice |
| Código | `src/`, `web/` | Solo si spec `active` y hay task |

La spec **no copia** enums. Enlaza.

## Ritual

1. Spec `reserved` → `active` (humano o docs-architect con mandato).
2. Enum nuevo: **primero** `tasks/README.md` y `.cursor/rules/data-contracts.mdc`.
3. Task `.aicontext/tasks/NN-*.md` mismo número.
4. Skill de módulo al abrir, no antes. Skills transversales (`metatracer-sdd`, `metatracer-platform`, safety, contracts, supply-chain) ya existen.
5. Código. Cierre: `backlog.md` + una línea en `MEMORY.md`.

## Stop

- Spec `reserved` y te piden código → para. No “adelantar” Fase 3–5 porque el enum exista.
- Dos docs se contradicen → para (`AGENTS.md` § cuándo preguntar).
- No crear tercera rule always-on de SDD; este skill basta.

## Checklist

- [ ] Estado de la spec es `active` antes de tocar `src/` o `web/` de producto.
- [ ] Número spec = número task.
- [ ] Diff no reabre TASK-00–35 como si fueran backlog.
- [ ] Cierre actualiza MEMORY, no reescribe el PRD entero.
