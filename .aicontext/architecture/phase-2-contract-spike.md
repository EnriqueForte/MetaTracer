# Fase 2 — spike de contrato

**Fecha:** 2026-09-26
**Estado:** Cerrada. No modifica `src/metatracer/`.
**Herramienta:** `openapi-typescript` **7.13.0** (OpenAPI 3.1). Node **v24.21.0** solo dentro de `spikes/web-v2-contract/.tools/`, fuera de git. No entra en `pyproject.toml` ni en la imagen Python.

## Qué se generó

| Archivo | Papel |
| :--- | :--- |
| `spikes/web-v2-contract/export_openapi.py` | Vuelca el schema de `create_app()` |
| `spikes/web-v2-contract/openapi.json` | Snapshot OpenAPI 3.1.0, paquete 0.6.0, 39 operaciones |
| `spikes/web-v2-contract/schema.d.ts` | Tipos generados. No editar |
| `spikes/web-v2-contract/package.json` | Solo la herramienta, versión fijada |
| `spikes/web-v2-contract/package-lock.json` | Lock de ese único paquete |

Regenerar, desde la raíz del repo, con el venv del proyecto:

```
.venv\Scripts\python.exe spikes\web-v2-contract\export_openapi.py
```

y después, con el Node del spike en el `PATH`:

```
npx --no-install openapi-typescript openapi.json -o schema.d.ts
```

Las rutas de webhooks se registran en el lifespan, no en la construcción de la app. El script llama a `register_webhook_routes` sin factory de sesión para que el snapshot coincida con un servidor ya arrancado. Un `create_app().openapi()` a secas omite `/api/webhooks` (34 operaciones en vez de 39).

## Qué queda cerrado en el tipo generado

Modelos con nombre, usables tal cual: `ScanRequest`, `RunCreatedResponse`, `RunStatusResponse`, `RunListResponse`, `FindingsResponse`, `FindingResponse` (`severity` admite `null`), scopes, usuarios, invitaciones, feedback, notificaciones, `SearchResponse`, `ImportResponse`, `ScopeImportResponse`, `WebhookCreate`, `WebhookUpdate`.

Los enums del cable salen como uniones de literales en minúsculas (`Severity`, `FindingType`, `RunStatus`, `ReasoningDepth`, `Confidence`, `UserRole`). `SearchHit.finding_type` y `SearchHit.severity` quedan como `string` porque el modelo Pydantic ya los declara así, no porque el generador los haya ensanchado.

`HTTPValidationError.ctx` es un objeto vacío en el schema de FastAPI. El cliente enseña `detail` como texto y no lee `ctx`.

## Huecos — no se cierran en esta fase

Cambiar un `response_model` es un cambio de contrato Python, con pytest y `safety-guardian`. No se ha hecho.

| Superficie | Tipo generado | Qué hace el código |
| :--- | :--- | :--- |
| `POST /api/auth/login`, `/setup`, `/register` | `{ [key: string]: unknown }` | `{ authenticated: true, username, role, csrf_token }`. En setup el rol es `operator`. En register el rol es el de la invitación |
| `POST /api/auth/logout` | objeto abierto | `{ ok: true }` |
| `GET /api/auth/me` | objeto abierto | `{ authenticated: false }` o `{ authenticated: true, username, role }` sin `csrf_token` |
| `GET /api/stats` | `runs`, `assets` y `agent_usage` son mapas de `number`. `findings`, `top_domains` y `top_evidence` son `unknown` | La forma estable está en `DashboardStatsService.build` (`services/dashboard.py`): `findings` tiene `total`, `severity_breakdown`, `by_type`, `unclassified`. `top_domains` es `{ domain, count }`. `top_evidence` lleva `signature`, `evidence_snippet`, `finding_type`, `occurrences`. `agent_usage` tiene `calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms` |
| `GET /api/runs/{id}/stream` | `200` como `application/json: unknown` | El cable es `text/event-stream`. El JSON de cada evento es `ProgressEvent` (`orchestrator.py`). No se documenta con `response_model`: FastAPI lo presentaría como JSON y el tipo mentiría |
| `GET /api/runs/{id}/export` y `POST /api/knowledge/export` | schema vacío | Son descargas (`FileResponse`). El cliente no parsea el cuerpo como JSON |
| `POST /api/scopes/import` y `POST /api/knowledge/import` | sin body en el schema; la respuesta sí está tipada | El cuerpo es el JSON portable en crudo |
| `GET/POST/PUT /api/webhooks` y deliveries | listas u objetos abiertos. El body de alta y update sí es `WebhookCreate` / `WebhookUpdate` | `_public` devuelve `id`, `name`, `url`, `event`, `headers` (valores `***`), `max_retries`, `active`, `created_at`. Una entrega devuelve `id`, `run_id`, `status`, `attempts`, `max_retries`, `status_code`, `last_error`, `created_at` |
| `DELETE /api/webhooks/{id}` | el schema dice **200** con cuerpo `unknown` | El handler devuelve **204** sin cuerpo |

Webhooks no tienen página en V1. El hueco no bloquea la paridad visual. Sí bloquea una UI futura de webhooks hasta que exista un modelo de respuesta.

## Regla para la fase 3 y las pantallas

`schema.d.ts` es la fuente de los modelos con nombre. Donde el tipo es un mapa abierto, la pantalla no inventa claves: o espera el cambio de contrato, o usa un overlay revisado contra la tabla de arriba. Auth y dashboard están en esa segunda lista. El SSE no se tipo contra el `200` generado.

La fase 3 (fundación Next, sin pantallas) sigue bloqueada por la lista npm y el proxy de un solo origen, no por este spike.
