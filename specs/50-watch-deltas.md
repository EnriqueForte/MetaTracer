# Spec 50 — Deltas watch: desaparecido y severity-up

**Estado:** closed  
**Agente previsto:** `pipeline-engineer` · UI compare: `v2-ui-engineer`  
**Skill al abrir:** `metatracer-platform`  
**Fuente leftover:** `.aicontext/features/12-platform-v3.md` Eje A · spec 44 OOS  
**Task:** [TASK-50](../.aicontext/tasks/50-watch-deltas.md)

## Intención

TASK-22/44 emiten solo findings **nuevos** (`new_findings` en el webhook). El Eje A
pedía también **desaparecidos** (estaban y ya no) y **severity-up**. Ampliar el
set cerrado `PAYLOAD_KEYS` exige esta spec; no se “cuela” en un fix.

Misma comparación determinista por `dedup_signature` / scope (sin LLM).

## Alcance previsto (cuando pase a active)

- Delta del watch frente al historial del mismo scope: `new` (ya existe),
  `resolved` (firma ausente en el run actual), `severity_up` (misma firma, severidad
  mayor según el orden del contrato).
- `PAYLOAD_KEYS` gana contadores **escalares** (`resolved_findings`,
  `severity_up_count`). Sigue siendo JSON plano; **no** arrays de evidencia ni
  snippets en el webhook.
- UI: reutilizar `/runs/compare` (ya distingue new / reappeared / severity_changed /
  resolved / persistent). Dashboard CTA si falta el puente watch → compare.
- CLI `watch` documenta los campos nuevos. Tests de contrato: payload con clave
  extra sigue rechazado salvo las nuevas.

## Fuera de alcance

Varios watches por scope. Windows Service. `@reboot`. Cron de 6 campos.
`apscheduler`. Arrays de findings en el webhook. Geocoding. Código mientras esta
spec esté `reserved`.

## Dependencias

Spec 44 closed. `PAYLOAD_KEYS` en `src/metatracer/api/webhooks.py`. Compare UI
(TASK-35). No toca embeddings ni conectores.
