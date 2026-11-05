# Spec 36 — Investigations y correlación

**Estado:** closed  
**Task:** [`.aicontext/tasks/36-investigations.md`](../.aicontext/tasks/36-investigations.md)  
**Agente:** `ui-engineer` (CLI) · backend/API ya en el árbol  
**Enums:** `.aicontext/tasks/README.md` → `investigation.status`, `correlation.kind`

## Intención

Agrupar runs de un engagement sin aislar clientes: una instalación sigue siendo un solo dominio
de confianza. Dos assets que comparten `value_hash` comparten un **valor**, no una identidad.
`author_string` no es `finding_type` (ADR-0009).

Una sugerencia de triaje de otro run del mismo grupo **no se aplica sola** y no cambia
`severity` ni la evidencia (regla 6).

## Alcance previsto (cuando pase a active)

- Entidad Investigation: agrupa `run_id`s; `status` `open` \| `closed`.
- Correlaciones por `correlation.kind` sobre valores normalizados (`normalized_kind` ya existe).
- API de listado/agrupación; CLI paridad mínima.
- El detector `internal_endpoint` (spec 37) alimenta `correlation.kind` homónimo; no bloquear 36 si 37 sigue reserved: usar solo kinds ya emitibles (`email`, `gps_point`, …).

## Fuera de alcance

Multi-tenant / workspaces. Copiar triage entre runs. OSINT o geocoding. UI (spec 43).

## Dependencias

v3.2 cerrado. TASK-36. Skill `metatracer-investigations`.
