# TASK-42: UI del operador (triage masivo y densidad)

**Módulo:** `api/runs.py`, `db/repositories.py`, CLI `findings`, `web/` findings panel  
**Spec:** [specs/42-ui-operator.md](../../specs/42-ui-operator.md)  
**Dependencias:** TASK-35  
**Agentes:** `v2-ui-engineer`, `ui-engineer` (API/CLI)  
**Estado:** **Cerrada 2026-11-05.**

## 1. Objetivo técnico

Triage masivo con los mismos estados que TASK-35. Solo operador + CSRF. No muta `severity`
ni `evidence_snippet`. Densidad en el panel de findings; virtualización usa `--mt-row-h`.
Atajo `x` para seleccionar la fila activa.

## 2. Subtareas

- `POST /api/runs/{run_id}/findings/triage` (`finding_ids` 1–200, `status`, `note`).
- `FindingRepository.set_triage_many` en una transacción.
- CLI `metatracer findings bulk-triage`.
- UI: checkboxes, barra de aplicación, confirmación, oculta a viewers.
- `DensitySwitch` en el panel; fila virtual lee el token de densidad.
- Regenerar OpenAPI / `schema.d.ts`.

## 3. Fuera de alcance

Investigations (43). Jinja/Alpine. CDN. SSO. Segundo host.

## 4. DoD

- [x] Bulk no toca severity/evidencia; viewer y CSRF fallan igual que el PUT unitario
- [x] Viewer no ve controles de selección
- [x] Virtualización + densidad; atajo `x`; paleta intacta
- [x] Spec 42 closed; MEMORY y backlog actualizados
