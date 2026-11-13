# TASK-50: Deltas watch desaparecido y severity-up

**Módulo:** `services/watch.py`, `api/webhooks.py`, CLI `watch`, UI compare/dashboard  
**Spec:** [specs/50-watch-deltas.md](../../specs/50-watch-deltas.md)  
**Dependencias:** TASK-22, TASK-35, TASK-44  
**Agentes:** `pipeline-engineer`, `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-13.**

## 1. Objetivo técnico

El watch ya cuenta hallazgos **nuevos** (`new_findings`) contra el historial
del mismo `allowed_scope`. Añadir dos contadores **escalares** al payload
cerrado del webhook:

- `resolved_findings` — identidades del último run **completed** del mismo
  scope que ya no están en el run actual.
- `severity_up_count` — misma identidad en ese par, severidad actual **mayor**
  según el orden del contrato (`info` < `low` < `medium` < `high` < `critical`).
  NULL no cuenta. Una bajada no cuenta.

`new_findings` no cambia: sigue siendo “nunca visto en ningún run anterior
del mismo scope”. Identidad = `finding_identity` (URL + tipo + snippet), no
`dedup_signature` (lleva `asset_id` distinto en cada run). Sin LLM. Sin
arrays ni snippets en el webhook.

## 2. Subtareas

- `DeltaResult` + `DeltaReporter.compute_delta`.
- `PAYLOAD_KEYS` + `enqueue_terminal` / orquestador (fallo → ceros, el run sigue).
- CLI `watch`: documentar e imprimir los tres contadores.
- UI: CTA compare con `a` = run anterior del mismo scope cuando existe;
  el dashboard apunta a `/runs/compare`.

## 3. Fuera de alcance

Varios watches por scope. Arrays de findings. Geocoding. Spec 51.

## 4. DoD

- [x] Payload webhook: solo claves de `PAYLOAD_KEYS`; extra se descarta
- [x] `resolved_findings` / `severity_up_count` son enteros ≥ 0
- [x] Primera iteración: resolved y severity-up = 0
- [x] Spec 50 closed
