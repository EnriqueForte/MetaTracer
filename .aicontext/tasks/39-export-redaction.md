# TASK-39: Redacción de exports (Fase 5)

**Módulo:** `reports/disclosure.py`, CLI `report --redact`, API `GET .../export?redact=`, UI Download  
**Spec:** [specs/39-export-redaction.md](../../specs/39-export-redaction.md)  
**Dependencias:** TASK-04, TASK-18  
**Agentes:** `pipeline-engineer` (motor), `ui-engineer` (API/CLI), `v2-ui-engineer` (selector)  
**Estado:** **Cerrada 2026-11-05.** Código y UI ya estaban en el árbol; esta slice activa el contrato SDD, desbloquea `export.redaction` y cubre `none`/`all`.

## 1. Objetivo técnico

Redactar **solo el fichero exportado**. La fila `Finding` (incl. `evidence_snippet`) no se escribe. Valores: `none` \| `contacts` \| `coordinates` \| `all`.

- `contacts` — emails → `[redacted-email]`
- `coordinates` — GPS/lat-lon → `[redacted-coordinates]`
- `all` — ambos
- API y CLI **default `none`**. UI de descarga **propone `contacts`**.

El JSON declara `redaction` y el Markdown incluye «Stored findings in the database were not modified.»

## 2. Subtareas

### 39.1 Contrato SDD

- Spec 39 `reserved` → `closed`.
- `export.redaction` deja de ser reserved-implementable.
- Skill `report-engine` documenta el modo.

### 39.2 Código (ya en el árbol)

- `Redaction` + `apply_redaction` en `reports/disclosure.py`.
- Orquestador aplica el modo al `ReportData` antes de los exportadores.
- CLI `metatracer report --redact` y query API, default `none`.
- `ExportLinks` default `contacts`; query `redact=` en el href.

### 39.3 Tests

- Copia redactada vs card original intacta (`contacts`, `coordinates`, `all`, `none`).
- UI: selector en `contacts` y href `redact=contacts`.

## 3. Fuera de alcance

Anonimizar el run en caliente. Cambiar `triage_status` al exportar. Conectores (38).

## 4. DoD

- [x] Default API/CLI `none`; UI propone `contacts`
- [x] BD no cambia
- [x] Tests de la slice verdes; ruff limpio
- [x] Spec 39 closed; MEMORY y backlog actualizados
