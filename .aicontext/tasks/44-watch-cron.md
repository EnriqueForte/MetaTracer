# TASK-44: Watch `--cron` (Eje A leftover)

**Módulo:** `services/cron.py`, CLI `watch`, `deploy/metatracer-watch.service`  
**Spec:** [specs/44-watch-cron.md](../../specs/44-watch-cron.md)  
**Dependencias:** TASK-22  
**Agentes:** `pipeline-engineer`, `test-engineer`  
**Estado:** **Cerrada 2026-11-05.** Parser stdlib; sin `apscheduler`.

## 1. Objetivo técnico

Cadencia calendario sin dependencia nueva. `--cron` es exclusivo de `--interval`.
`--once` no se combina con `--cron`. Expresión en UTC. Fallo de parseo = exit 1
antes de escanear.

## 2. Subtareas

- Parser 5 campos: `*`, `n`, `a-b`, `a,b`, `*/n`, `a-b/n`; aliases `@hourly` …
  `@yearly`. `7` en DOW = domingo.
- `next_fire(after)` minuto a minuto, techo 366 días.
- CLI `--cron`; mutex con `--interval` / `--once`.
- Loop: sleep hasta el próximo fire; backoff de fallos sigue mandando.
- `deploy/metatracer-watch.service` (placeholders; sin `ALLOW_LOOPBACK`).
- Compose profile `watch` (scope por variable; no arranca en el default).

## 3. Fuera de alcance

Windows SCM. PAYLOAD_KEYS nuevos. Redis. Varios watches por scope.

## 4. DoD

- [x] Parser unitario (válido / inválido / next UTC)
- [x] CLI: help, mutex, cron malformado
- [x] Cero deps nuevas; ruff limpio
