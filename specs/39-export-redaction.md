# Spec 39 — Redacción de exports (Fase 5)

**Estado:** closed (2026-11-05)  
**Agente previsto:** `pipeline-engineer` (`reports/`) · `ui-engineer` / `v2-ui-engineer` (opción de descarga)  
**Enum:** `export.redaction` en `.aicontext/tasks/README.md`  
**Task:** [TASK-39](../.aicontext/tasks/39-export-redaction.md)

## Intención

Redactar **solo el fichero exportado**. La base no cambia. API y CLI default `none`.
La UI de descarga propone `contacts`.

Valores: `none` \| `contacts` \| `coordinates` \| `all`. GPS y emails son el caso de uso;
no borrar `evidence_snippet` en DB.

El código (`reports/disclosure.py`, `--redact`, query `redact`, selector en Download) ya
estaba en el árbol; TASK-39 lo desbloquea en SDD.

## Fuera de alcance

Anonimización en caliente del run. Cambiar `triage_status` al exportar.

## Dependencias

Motor de reportes TASK-04/18. Skill `report-engine`.
