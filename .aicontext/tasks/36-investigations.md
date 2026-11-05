# TASK-36: Investigations y correlación (CLI + contrato SDD)

**Módulo:** Fase 3 — agrupación de runs y valores compartidos  
**Spec:** [specs/36-investigations.md](../../specs/36-investigations.md)  
**Dependencias:** TASK-35 (triage), v3.2  
**Agentes:** `pipeline-engineer` (ya en `src/`), `ui-engineer` (CLI)  
**Estado:** **Cerrada 2026-11-05.** Backend/API ya estaban; CLI `investigation` y contrato SDD añadidos en esta slice.

## 1. Objetivo técnico

Una investigation agrupa `run_id`s. No aísla clientes. El triaje de otro run del grupo se **sugiere** y no se copia. Dos assets con el mismo `value_hash` comparten un valor, no una identidad (`author_string` no es `finding_type`).

El modelo, migraciones Alembic, API `/api/investigations`, correlaciones, sugerencias de triage y paneles en la vista de run **ya están en el árbol**. Faltaba el contrato TASK + paridad CLI exigida por la spec.

## 2. Subtareas

### 36.1 Contrato SDD

- Spec 36 `active` → `closed` al cumplir DoD.
- `investigation.status` y `correlation.kind` dejan de ser reserved-implementable.
- Skill `metatracer-investigations`.
- Esta task numerada; mapeo en `tasks/README.md`.

### 36.2 CLI `metatracer investigation`

Grupo Typer, misma BD que el resto de comandos, un `asyncio.run` por invocación:

- `list` — nombre, status, recuento de runs
- `show <id>` — detalle y runs del grupo
- `create <name> [--description]`
- `close <id>` — `status=closed`; no acepta attach
- `attach <id> <run>` — `run` por UUID o prefijo (`RunRepository.resolve`)
- `detach <id> <run>`

Conflictos (`InvestigationConflictError`) → exit 1. No muta `severity` ni evidencia.

### 36.3 Tests

- Help del grupo.
- create → list → attach → show → close → attach rechazado.
- DB aislada (`METATRACER_DATABASE_URL` en tmp).

## 3. Fuera de alcance

UI nueva (spec 43). Detector `internal_endpoint` (spec 37). Copiar triage. Multi-tenant. OSINT.

## 4. DoD

- [x] CLI list/show/create/close/attach/detach
- [x] Cerrado no admite attach
- [x] Tests de la slice verdes; ruff limpio
- [x] Spec 36 closed; MEMORY y backlog actualizados
