# Contrato HTTP que Web V2 debe consumir

Fuente de verdad de implementación: código en `src/metatracer/api/` y `src/metatracer/services/orchestrator.py`. El snapshot generado el 2026-09-26 está en `spikes/web-v2-contract/` (`openapi.json`, `schema.d.ts`). Este documento dice qué se reutiliza y qué huecos tiene ese schema. La nota de la fase está en [phase-2-contract-spike.md](../architecture/phase-2-contract-spike.md).

Idioma de los valores de enum en el cable: minúsculas. Title Case es presentación.

## Estrategia de tipos

1. FastAPI publica `/openapi.json` (no hay override de `docs_url` en `create_app`). Las rutas de webhooks se registran en el lifespan: un `create_app().openapi()` sin ese registro no las incluye. El spike las añade llamando a `register_webhook_routes` antes de serializar, sin abrir la base de datos.
2. Web V2 genera tipos TypeScript desde ese schema con `openapi-typescript` **7.13.0** (fijado en la fase 2). El archivo generado no se edita a mano. Hoy vive en `spikes/web-v2-contract/schema.d.ts`.
3. Zod se escribe solo en formularios (scan, login, setup, register, scope, usuario, invitación, feedback). Si el servidor responde 422, gana el servidor.
4. Donde el schema sea un objeto abierto (`auth`, `DashboardStatsResponse.findings` / `top_domains` / `top_evidence`, respuestas de webhooks) el tipo generado es `{ [key: string]: unknown }`. No se completa inventando campos en el cliente. Esos huecos están listados en la nota de la fase 2. Cerrarlos en Python es un cambio de contrato, no un detalle de esta fase.
5. Prohibido duplicar el catálogo de rutas en constantes mágicas dispersas. Un módulo `web/src/lib/api/` importará los tipos generados cuando exista la app.

## Códigos y errores

Forma habitual: `{"detail": "<string>"}` o, en 422 de Pydantic, `{"detail": [{"loc", "msg", "type", ...}]}`.

| Código | Cuándo importa a la UI |
| :--- | :--- |
| 200 | Lecturas y la mayoría de updates |
| 201 | Alta de scope, usuario, invitación, import de scope |
| 202 | `POST /api/runs` — cuerpo `{ "run_id": string }`. La UI navega; no espera el resultado del scan en esta respuesta |
| 204 | Deletes |
| 401 | Credenciales o sesión |
| 403 | CSRF, rol viewer en una mutación, o `ScopeNotConfirmedError` |
| 404 | Run, scope, usuario, finding, auth desactivado en register/setup |
| 409 | Scan ya en curso (`ScanAlreadyRunningError`), nombre de scope duplicado, último operator, username |
| 413 | Body demasiado grande |
| 422 | Validación (scope vacío, mezcla de fuentes de scope, cursor malformado, password) |
| 429 | Rate limit. Header `Retry-After`. El stream SSE está exento |
| 503 | Knowledge o import de scope no disponibles en ese backend |

El 409 de “otro scan en curso” depende de `METATRACER_MAX_CONCURRENT_RUNS` (default 1). La UI no debe asumir que siempre es 1, ni debe ocultar el 409.

## Enums que la UI pinta y no calcula

| Contrato | Valores |
| :--- | :--- |
| `finding_type` | `gps`, `email`, `internal_path`, `software_version`, `debug_comment` |
| `severity` | `critical`, `high`, `medium`, `low`, `info`, o `null` (aún sin clasificar) |
| `confidence` | `high`, `medium`, `low` |
| `reasoning_depth` | `brief`, `standard`, `detailed` |
| `run.status` | `pending`, `running`, `completed`, `failed`, `aborted` |
| `extraction_status` (asset issue) | `failed`, `skipped` (los `ok` no viajan en `asset_issues`) |
| `skip_reason` | `unsupported_type`, `too_large`, `out_of_scope`, `duplicate_hash`, `empty_body` |
| `user.role` | `operator`, `viewer` |
| `feedback` vote | `up`, `down` |
| export `format` | `md`, `json`, `html`, `csv`, `bounty` |

`Finding.severity` puede ser `null`. La UI no inventa una severidad. El orden de la lista lo trae el API (el no clasificado va al final). El cliente no reordena por una severidad calculada.

## Auth, cookies, CSRF

Definido en `src/metatracer/api/auth.py`.

| Pieza | Valor |
| :--- | :--- |
| Cookie de sesión | `metatracer_session`, HttpOnly, `SameSite=Lax`, `Path=/`, `Secure` solo si el hop es HTTPS |
| Cookie CSRF | `csrf_token`, no HttpOnly, mismos `SameSite` / `Path` / `Secure` |
| Header | `x-csrf-token` (el servidor lee el nombre en minúsculas) |
| Mutaciones con sesión | CSRF + rol `operator` (`require_operator_action`) |
| GET de datos, incluido SSE | Sesión si auth está on; sin CSRF; `viewer` puede leer |
| Login, setup, register | CSRF previo a la sesión (la página lo deja en cookie). Auth off: estas rutas no abren sesión útil; register y setup responden 404 si auth está off |
| `GET /api/auth/me` | `{authenticated:false}` o `{authenticated, username, role}` |

Web V2 no guarda la sesión en `localStorage`. No hay Bearer. El navegador manda la cookie porque el origen es el mismo.

Con auth off, los dependencies de usuario son no-op y la UI de V1 no pide login. Web V2 tiene que leer el mismo modo (por ejemplo `GET /api/auth/me` o el comportamiento real del 401) y no inventar una pantalla de login cuando el servidor tiene auth desactivado.

## Scan — `POST /api/runs`

Modelo `ScanRequest` en `services/orchestrator.py`. Es el body exacto. Las opciones de export **no** van en este body.

```
targets:            string[]          (min 1, sin blancos)
scope_domains:      string[] | null
scope_confirmed:    boolean           (obligatorio; false → 403, sin run)
reasoning_depth:    brief|standard|detailed   (default standard)
scope_id:           string | null     (alias histórico de un solo id)
scope_ids:          string[] | null
watch:              boolean           (default false; marca iteración headless)
```

Exactamente una fuente de scope: `scope_domains` **o** `scope_id` **o** `scope_ids`. Nunca mezcla. El wizard de V1 envía `scope_ids` o `scope_domains`, no `scope_id` ni `watch`. Web V2, en paridad, hace lo mismo. `watch: true` es capacidad de CLI/API, no una casilla nueva de la migración.

El scope no se deduce de los targets. Lo escribe el operador.

Respuesta 202: `RunCreatedResponse.run_id`.

## Run y findings

| Método | Ruta | Respuesta |
| :--- | :--- | :--- |
| GET | `/api/runs?status&limit&cursor` | `RunListResponse`: `total`, `runs[]`, `has_more`, `next_cursor` |
| GET | `/api/runs/{run_id}` | `RunStatusResponse` |
| GET | `/api/runs/{run_id}/findings?severity&finding_type&confidence&q` | `FindingsResponse` |
| GET | `/api/runs/{run_id}/export?format=` | Fichero (`FileResponse`) |
| GET | `/api/runs/{run_id}/stream` | SSE |

`RunStatusResponse`: `run_id`, `status`, `target`, `scope[]`, `reasoning_depth`, `total_assets`, `total_findings`, `error_message`, `started_at`, `completed_at`, `asset_issues[]` (`asset_id`, `source_url`, `status`, `skip_reason`, `error_message`).

`FindingResponse`: `id`, `title`, `finding_type`, `type_label`, `severity | null`, `confidence`, `field_source`, `evidence_snippet`, `severity_justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps[]`, `asset_source_url`, `asset_final_url`, `asset_content_type`.

Esos campos de prosa son la “AI analysis” que existe. No hay otro recurso REST de análisis.

## SSE

Implementación: `ProgressBus` (`services/progress.py`) y `stream_run` (`api/runs.py`).

Evento (`ProgressEvent`):

```
run_id, stage, current_step, total_steps, message, current_asset | null
```

Wire: `data: {json}\n\n`. Comentarios `: keep-alive\n\n` cada 15 s sin evento. El cliente `EventSource` ignora los comentarios.

| `stage` | Papel |
| :--- | :--- |
| `scope_validation` … `report_generation` | Pasos 1–7 |
| `completed` | Fin correcto. `current_step == 7` |
| `failed` | El stream se cierra. Puede corresponder a `run.status` `failed` **o** `aborted` |

El stream hace replay del historial al conectar (tarde o tras reconectar). Si el último evento ya es terminal, no se registra suscriptor vivo: se entrega el historial y se acaba.

No hay `Last-Event-ID` ni id de evento SSE. La reconexión correcta es abrir otro `EventSource`: el servidor reenvía desde el principio. El cliente debe ser idempotente (el último evento de cada stage gana; no acumular contadores).

Cancelación: no existe. `ScanOrchestratorService.shutdown()` cancela tasks del proceso; no es una API pública. Web V2 no dibuja un botón Abort que no tenga endpoint.

Cuando el backend muere a mitad: `EventSource.onerror`. Comportamiento V1 a conservar: cerrar el stream y hacer polling de `GET /api/runs/{id}` cada 2 s hasta status terminal. Si el GET también falla, se muestra error de transporte, sin marcar el run como `failed` en cliente (el status lo dice el servidor, o se desconoce).

## Resto de la API que la UI V1 ya usa

| Método | Ruta | Uso V1 |
| :--- | :--- | :--- |
| GET | `/api/health` | Liveness. Sin sesión |
| GET | `/api/stats` | Dashboard. `DashboardStatsResponse` (`runs`, `assets`, `findings`, `top_domains`, `top_evidence`, `agent_usage`). Varios campos son dicts abiertos: la UI solo pinta lo que V1 pinta, ver matriz |
| GET/POST | `/api/scopes` | Lista y alta |
| GET/PUT/DELETE | `/api/scopes/{scope_id}` | |
| POST | `/api/scopes/import` | Body JSON portable crudo, no un modelo de formulario |
| GET/DELETE | `/api/notifications`, `/api/notifications/{index}` | Cola en memoria. El índice es el de la lista newest-first; un índice viejo es 404. Se vacía al reiniciar el proceso |
| GET/PUT/DELETE | `/api/feedback/{finding_id}` | Voto `up`/`down`, severidades before/after. No sube severidad por su cuenta: el servidor aplica la regla de feedback |
| POST | `/api/auth/login`, `/logout`, `/setup`, `/register` | |
| GET/POST | `/api/users` | Operator |
| PATCH/DELETE | `/api/users/{user_id}` | |
| GET/POST | `/api/invitations` | El código en claro solo viaja en la respuesta de creación |
| DELETE | `/api/invitations/{invitation_id}` | |

## API existente sin página V1

No es paridad. No se implementa en la migración. Se documenta para que nadie la “complete” de paso:

| Rutas | Superficie real hoy |
| :--- | :--- |
| `GET /api/knowledge/search`, `POST /api/knowledge/export`, `POST /api/knowledge/import` | CLI `kb` |
| `GET/POST /api/webhooks`, `PUT/DELETE /api/webhooks/{id}`, `GET .../deliveries` | CLI `watch --webhook` y el dispatcher. Respuestas `dict` / `list[dict]`, headers redactados en el listado |
| `watch: true` en `POST /api/runs` | CLI `watch`. Mismas etapas y mismos gates |

## Páginas HTML (V1, no son el contrato de datos)

`pages.py`, fuera de OpenAPI: `GET /`, `/runs`, `/runs/{run_id}`, `/scopes`, `/dashboard`, `/login`, `/register`, `/setup`, `/users`.

Web V2 no hace scrape de ese HTML. Solo usa JSON, SSE y descargas.

## Seguridad del contrato

- 403 de scope y 403 de CSRF/rol comparten código. El cliente puede mostrar el `detail`, como texto, sin reinterpretar el código como “scope inválido” si el mensaje es de CSRF.
- `error_message` y `message` del SSE están sanitizados en servidor y aun así se pintan como texto: pueden contener fragmentos del objetivo.
- Las descargas son `GET` con la cookie. No se construye la URL de export concatenando input del usuario más allá de `run_id` (UUID) y `format` del enum.
- `asset_source_url` / `asset_final_url` / `source_url` no son href hasta pasar `safeUrl`.
