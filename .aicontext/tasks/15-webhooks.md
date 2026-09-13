# TASK-15: Webhooks de salida + run_ref (v2.2)

**Módulo:** Integraciones — egreso operacional a canales de terceros
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md)
**Dependencias:** TASK-00 … TASK-14 (v1.0–v2.1 cerradas), fase v2.2
**Estado:** **Cerrada y validada 2026-09-13** (schema + CRUD API + dispatcher + relay buffer) — whook integrado en el repo en el commit `71df7a7`; verificado localmente `pytest -m "not e2e"` **435 passed** + `ruff check src tests` limpio (incluye test anti-SSRF del egreso). Revisión de seguridad: 1 hallazgo Medium (egreso sin `NetworkSafetyGuard`) **corregido y re-verificado**.

---

## 1. Objetivo técnico

Primer entregable del bloque **"integraciones"** de v2.2 (que amplía v2.1+).
Hoy el único canal de notificación terminal es la campana en memoria de la Web
UI (TASK-12): si el proceso se reinicia, los eventos se pierden y el operador
no puede encadenar con Slack/Teams/Discord un run completado con hallazgos.

El **webhook de salida** permite al operador subscribir un endpoint HTTPS a los
eventos terminales (`completed` / `failed`). Cada evento se persiste como fila
de **relay buffer** (`webhook_delivery`), idempotente por
`(webhook_id, run_id)`, y se entrega por HTTP con reintentos con backoff y cap
de intentos. Un webhook roto **nunca** falla el scan (regla 5).

Qué aporta de producto:

- Un run terminado puede notificar a Slack/Discord/Teams/canal propio sin que
  el pipeline dependa de esos endpoints (fire-and-forget).
- La fila de delivery sobrevive reinicios: al siguiente evento terminal el
  dispatcher recupera pendientes (`recover_pending`).
- `run_ref`: etiqueta corta y legible del run para URLs/reportes/payloads.

---

## 2. Subtareas

### 15.1 Contratos

Nuevos enums:

| Enum | Valores |
| :--- | :--- |
| `WebhookDeliveryStatus` | `pending` \| `succeeded` \| `failed` \| `rejected` |

Nuevas tablas (se crean solas con `create_all`, sin migración):

| Tabla | Columnas clave |
| :--- | :--- |
| `webhook_config` | `id` UUID, `name`, `url` (HTTPS), `event` (terminal), `headers` (JSON), `signature_secret_hash` (SHA-256 local), `max_retries`, `active`, `created_at` |
| `webhook_delivery` | `id` UUID, `webhook_id` FK, `run_id` FK, `status`, `attempts`, `max_retries`, `payload_json` (caché del body exacto), `status_code`, `next_retry_at` (epoch float), `last_error` (sanitized), `created_at` |
| unique | `(webhook_id, run_id)` — idempotencia del relay buffer |

En `Run` se añade `run_ref` (str corto, único, indexado) con `default_factory`
Python + `server_default` SQLite para que el `ALTER TABLE` de una BD existente
funcione sin migración real.

Actualizar antes de persistir valores nuevos: `.aicontext/tasks/README.md` y el
skill de contratos si procede.

### 15.2 Repositorios

En `metatracer/db/repositories.py`:

- `WebhookConfigRepository`: `create/get/update/delete/list_all`,
  `list_active_by_event`.
- `WebhookDeliveryRepository`: `create/get/update/delete`,
  `get_by_webhook_run` (única), `list_by_webhook`, `list_pending(limit)`
  (fila retriable por `next_retry_at <= now`, para el sweep de reinicio).

### 15.3 API CRUD (`metatracer/api/webhooks.py`)

`register_routes(app, session_factory=None)` (patrón `request.app.state`,
igual que feedback/scopes):

| Método | Ruta | Código | Comportamiento |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/webhooks` | 200 | Lista configs; **nunca** el hash del secreto ni los valores de headers (redacted `***`) |
| `POST` | `/api/webhooks` | 201 | Crea config; URL obligatoria **HTTPS**; evento terminal; secreto opcional → hash SHA-256 local |
| `PUT` | `/api/webhooks/{id}` | 200 / 404 | Replace de campos; nuevo secreto rota el hash |
| `DELETE` | `/api/webhooks/{id}` | 204 / 404 | Borra config (sin tocar deliveries: auditoría) |
| `GET` | `/api/webhooks/{id}/deliveries` | 200 / 404 | Estado de entregas (también vista de reintentos pendientes) |

### 15.4 Dispatcher (`WebhookDispatcher`, mismo módulo)

- `enqueue_terminal(run_id, status, *, target, total_assets, total_findings,
  executive_summary, error_message)`:
  - `status` no terminal → no-op;
  - `recover_pending()` oportunista antes de añadir nuevas filas;
  - por cada `WebhookConfig.active` con `event == status`: construye payload
    plano (claves fijas `PAYLOAD_KEYS`), comprueba idempotencia, persiste fila,
    lanza `asyncio.create_task` con retención en `self._tasks`;
  - nunca lanza (regla 5).
- `_build_payload`: `run_id`, `run_ref`, `event`, `target`, `total_assets`,
  `total_findings`, `executive_summary` (truncado 300), `error_message`
  (sanitizado). **Keys fijas**; si un render añadiera claves extra se descartan
  (defensa contra fugas de metadata).
- `_attempt`: intenta enviar; 2xx → `succeeded`; 4xx → `rejected` (no
  reintenta); red/5xx → backoff exponencial (`base * 2^(attempts-1)`, cap) hasta
  `max_retries` → `failed`.
- `_send`: cliente `httpx` dedicado (HTTPS, sin redirects, timeouts cortos,
  body nunca leído). **No usa `safe_httpx_request`**: el webhook es egreso
  operacional fuera del scope del run, no un asset en-scope. Aun así aplica la
  **invariante 7 al egress**: antes de abrir socket resuelve el host
  (`urlsplit` → `NetworkSafetyGuard.check(host, port)`, inyectado por
  `app.py` con `settings.allow_loopback`); loopback/privadas/link-local/
  metadata cloud → rechazo sin conexión.
- `recover_pending` / `shutdown`.

### 15.5 Orquestador

- `ScanOrchestratorService(..., webhooks=...)` opcional (análogo a
  `notifications`).
- `_finalize_run` → `_notify_run_finished` ahora async: publica la campana
  (TASK-12) **y** llama `webhooks.enqueue_terminal(...)` en el mismo bloque
  `try/except` (regla 5).

### 15.6 App lifespan

- `create_app`: `WebhookDispatcher(session_factory, guard=NetworkSafetyGuard(settings.allow_loopback))`
  en `app.state`, inyección en el orquestador,
  `register_webhook_routes(app, factory)`,
  `await dispatcher.shutdown()` en shutdown.

### 15.7 Safety y persistencia

- **Cero bytes de archivos** en payloads (solo escalares/counters).
- **HTTPS obligatorio** validado en write y re-chequeado en send.
- **Anti-SSRF en el egreso** (invariante 7, revisión de seguridad v2): el
  `NetworkSafetyGuard` bloquea loopback/privadas/link-local/metadata cloud
  antes del socket; `follow_redirects=False` evita el bypass por redirect
  (no hay hops). Test de regresión:
  `test_send_rejects_loopback_target_even_with_https`.
- El secreto de firma **nunca** se persiste en claro: solo su hash SHA-256.
- Headers y URL se sanitizan en logs; el body de respuesta nunca se lee.
- El payload **no** incluye snippets de evidencia ni metadata cruda: solo
  counters + summary. La evidencia sensible nunca abandona la máquina vía webhook.
- Las entregas son visibles por API (read-only) pero **no** se exportan en
  reportes de bounty (anotaciones internas fuera de reportes).

---

## 3. Fuera de alcance

- Firma HMAC end-to-end del payload (el diseño guarda solo el hash del
  secreto; rotación/edge de firma sería otro slice con materia de gestión de
  secretos).
- Webhooks de entrada (acciones remotas que disparen scans).
- Fila de reintentos persistida como worker separado / cron (el sweep es
  oportunista en el siguiente evento terminal).
- Multi-tenant/auth de los endpoints; autenticación del API.

---

## 4. Tests mínimos

- `tests/unit/test_webhook_dispatcher.py` — enums/nanoid `run_ref` (formato,
  unicidad); CRUD de `WebhookConfigRepository`+`WebhookDeliveryRepository`;
  delivery idempotente por `(webhook_id, run_id)`; `list_pending` solo con
  `next_retry_at` vencido; `enqueue_terminal` no-op para
  eventos no terminales/inactivos; idempotencia; payload con keys fijas;
  `_send` con fake transport: 2xx→succeeded, 4xx→rejected sin retry,
  5xx/error→retry hasta cap→failed; `recover_pending` re-encola con la misma
  `payload_json` cacheada; **anti-SSRF**: `_send` rechaza host loopback con el
  `NetworkSafetyGuard` real antes de abrir socket.
  (Inicialmente se planearon `test_webhook_models.py`/`test_webhook_repositories.py`
  separados; se consolidaron en este fichero por cercanía con el dispatcher.)
- `tests/integration/test_api_webhooks.py` — CRUD completo; 422 URL no HTTPS;
  422 evento no terminal; headers redacted en GET; GET deliveries 404 si no
  existe el webhook.
- Suite: `pytest -m "not e2e"` en verde y `ruff check src tests` limpio.

---

## 5. Criterios de aceptación (DoD)

- [x] Un operador crea un webhook HTTPS vía `POST /api/webhooks` y recibe una
      entrega `succeeded` (contra un mock) al completar un run.
- [x] Reintentar/doblar el mismo run no duplica filas de delivery
      (idempotencia por `(webhook_id, run_id)`).
- [x] Un webhook caído no aborta ni retrasa el run (fire-and-forget; el
      fallo queda en `webhook_delivery` con `last_error` sanitizado).
- [x] Tras un reinicio simulado, `recover_pending` re-encola entregas antiguas
      sin enviar payload distinto (misma `payload_json` cacheada).
- [x] El payload de salida contiene solo las claves de `PAYLOAD_KEYS` y
      **ninguna** evidencia/metadata cruda.
- [x] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio.