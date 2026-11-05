---
name: metatracer-investigations
description: Investigations y correlación de MetaTracer (Fase 3) — agrupar runs, sugerir triage sin copiarlo, ValueEntity por correlation.kind. Usar al tocar services/investigation.py, correlation.py, detectors/correlate.py, api/investigations.py, CLI investigation o TASK-36.
---

# Investigations y correlación

Fuente: [TASK-36](../../../.aicontext/tasks/36-investigations.md), [spec 36](../../../specs/36-investigations.md).
Enums: `.aicontext/tasks/README.md` (`investigation.status`, `correlation.kind`).

## Qué es

- `Investigation` agrupa runs (`Run.investigation_id` nullable). Cerrar no oculta runs.
- Una instalación = un dominio de confianza. No hay workspaces.
- `suggestions_for` ofrece triage decisivo de otro run del grupo. **Nunca escribe** `triage_status`, `severity` ni evidencia (regla 6).
- `ValueEntity` + `AssetValue`: hash de valor normalizado. No es identidad.
- `author_string` es `correlation.kind`, no `finding_type` (ADR-0009).
- `internal_endpoint` como correlación lo escribe el detector homónimo (TASK-37). `cloud_storage` no es kind.

## API

`/api/investigations` CRUD + attach/detach. 409 = nombre o run ya agrupado. 404 = missing.

## CLI

`metatracer investigation list|show|create|close|attach|detach`. Misma semántica que el API.

## Stop

- No auto-aplicar sugerencias.
- No geocoding / grafo de personas.
- No emitir `internal_endpoint` findings aquí: salen de `detectors/network.py`.
