# Spec 44 — Watch cron (Eje A leftover)

**Estado:** closed (2026-11-05)  
**Agente previsto:** `pipeline-engineer`  
**Fuente:** `.aicontext/features/12-platform-v3.md` Eje A · TASK-22  
**Task:** [TASK-44](../.aicontext/tasks/44-watch-cron.md)

## Intención

Sustituir el leftover `--cron` de TASK-22 con un crontab de **5 campos en UTC**,
parseado en stdlib. Cero paquetes nuevos (`apscheduler` no entra). El bucle sigue
siendo `asyncio.sleep` hasta el próximo disparo. Mismo `ScanOrchestratorService`,
mismo lock por scope, mismo delta `new_findings`.

Operación: unidad systemd de ejemplo en `deploy/` y un servicio compose con
profile `watch`. El binario no se convierte en daemon: systemd/Docker lo
supervisan.

## Fuera de alcance

Windows Service. `@reboot`. Segundos (6 campos). `apscheduler`. Deltas
“desaparecido” / “severity-up” (ahora [spec 50](50-watch-deltas.md) closed).
Varios watches concurrentes por scope.

## Dependencias

TASK-22 cerrado. Skill `metatracer-platform` + supply-chain (sin extra).
