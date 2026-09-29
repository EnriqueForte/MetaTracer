# Fase 10 — reportes

**Fecha:** 2026-09-29
**Estado:** Cerrada.

En un run `completed` hay cinco enlaces, y solo esos formatos:

`/api/runs/{run_id}/export?format=` con `md`, `json`, `html`, `csv` y `bounty`.

El `run_id` va codificado. El formato no es un texto libre. También están History y New scan, como en V1.

Se comprobó en un run local terminado: los cinco `href` apuntan a `/api`, no a `/v2/api`.
