# Spec 41 — Higiene operativa

**Estado:** closed (2026-11-05)  
**Agente previsto:** `ui-engineer` (API/orquestador) · `pipeline-engineer` (locks) · `test-engineer` (DoD)  
**Task:** [TASK-41](../.aicontext/tasks/41-ops-hygiene.md)

## Intención

Cerrar limitaciones **aceptadas** en v3.2, no reabrir TASK-28/33:

- Lock de scan durable entre procesos (filas abiertas en BD + `concurrency_gate`).
- Re-cola de un run `aborted` (run nuevo; no se reanuda a mitad de pipeline).
- Métricas Prometheus **sin** dependencia nueva (texto en `GET /api/metrics`).
- Versionado `/api/v1` como alias de `/api`, mismo origen; `web/` no cambia.

## Fuera de alcance

HA Redis/ARQ (OOS de v3). DNS-rebinding IP pin y NAT64 (OOS TASK-32). Watch cron (no priorizado). OpenTelemetry SDK.

## Dependencias

TASK-28, TASK-33. Skill `metatracer-platform`.
