# TASK-41: Higiene operativa

**Módulo:** lock durable, resume de `aborted`, métricas, `/api/v1`  
**Spec:** [specs/41-ops-hygiene.md](../../specs/41-ops-hygiene.md)  
**Dependencias:** TASK-28, TASK-33  
**Agentes:** `pipeline-engineer`, `ui-engineer`, `test-engineer`  
**Estado:** **Cerrada 2026-11-05.** Sin dependencias nuevas (métricas = texto Prometheus stdlib).

## 1. Objetivo técnico

Cerrar limitaciones aceptadas en v3.2:

- Lock de scan **durable** entre procesos (`concurrency_gate` + filas `pending`/`running`).
- Re-cola de un run `aborted` (run **nuevo**; el original sigue aborted). No se reanuda a mitad de ingesta.
- `GET /api/metrics` en exposición Prometheus, stdlib, sin `prometheus_client`.
- Alias `/api/v1/*` → `/api/*`. Un origen. El cliente `web/` sigue en `/api`.

## 2. Subtareas

- Tabla `concurrency_gate` (SQLite `create_all` + seed; Alembic `c9e4b2a17d03`).
- `_create_run` rechaza si hay ≥ `METATRACER_MAX_CONCURRENT_RUNS` abiertos en BD.
- `POST /api/runs/{id}/resume` (202) y CLI `metatracer resume`.
- Middleware de rewrite `/api/v1`.
- Métricas: gauges por `run.status`, slots abiertos, límite.

## 3. Fuera de alcance

HA Redis/ARQ. DNS-rebinding / NAT64. Watch cron. OpenTelemetry SDK. Continuar un abort a mitad de un asset.

## 4. DoD

- [x] Segundo proceso no supera el límite solo porque su semáforo está vacío
- [x] Resume solo si `aborted`; 409 en otro estado
- [x] `/api/v1/health` = `/api/health`
- [x] `/api/metrics` texto Prometheus; sin paquete nuevo
- [x] Tests de la slice verdes; ruff limpio
