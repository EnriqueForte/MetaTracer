# Matriz de paridad Web V1 → Web V2

Recorrida el 2026-09-29; **Setup cerrado el 2026-10-24 (T9)**; **corte ejecutado el
2026-10-24 (T11, [ADR-0016](../decisions/0016-web-v2-replaces-v1.md))**. Todas las filas de
pantalla V1 están en `verified` y **la tabla se considera `migrated`**: Web V1 ya no existe en
el producto. CLI, pipeline y lo no implementado en V1 siguen en `out_of_scope`. El detalle está
en [phase-14-parity.md](../architecture/phase-14-parity.md).

Leyenda de estado: `not_started` | `in_progress` | `verified` | `out_of_scope` | `missing` (regresión: bloquea el corte).

“V2 previsto” es el destino en `web/`, no un archivo existente. Las rutas V2 cuelgan de `basePath` `/v2`.

## Producto que el operador ya usa en el navegador

| V1 Feature | V1 Implementation | V2 previsto | API | Seguridad | Test | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Shell, sidebar, skip-link | `templates/base.html`, `pages.py` | Layout `/v2` | — | CSP, sin HTML de usuario en el shell | RTL del skip-link; Playwright de nav | verified |
| Aviso ético | `base.html`, texto fijo EN | Mismo texto, no editable por API | — | Texto fijo, no viene del target | Assert del copy | verified |
| Campana de notificaciones | `notifications_bell` en `base.html` | Client component | `GET/DELETE /api/notifications` | `kind` y `target` como texto; índice de borrado es el de la lista | RTL + API | verified |
| Sign out | `MetaTracerUI.logout` | Mismo POST con CSRF | `POST /api/auth/logout` | CSRF; limpia sesión también para V1 | Playwright auth on | verified |
| Reconnaissance / wizard | `index.html` `scanWizard` | `/v2` | `GET /api/scopes`, `POST /api/runs` | Scope no inferido del target; una sola fuente | Playwright | verified |
| Modal de scope | `index.html`, checkbox no premarcado, título `Confirm authorized scope` | Dialog de dominio, no un alert genérico | Body `scope_confirmed: true` solo tras el check | Gate de UX; el 403 del servidor manda si se fuerza el POST | RTL: botón disabled; e2e del 202 | verified |
| Reasoning depth | `<select>` con enum de `pages.py` | Mismo enum | Campo de `ScanRequest` | El cliente no añade valores | Contract test del body | verified |
| Errores 403 / 404 / 409 / 429 del alta | `startScan` en `index.html` | Mismos textos de UI acordados en el plan | Códigos de `create_run` | `detail` como texto | RTL con fetch mockeado + un e2e 409 | verified |
| Redirect tras 202 | `location.assign('/runs/' + encodeURIComponent(run_id))` | `/v2/runs/{id}` con id codificado | `RunCreatedResponse` | No concatenar el id en HTML | e2e | verified |
| Progreso SSE, 7 etapas | `run.html` `EventSource` | `lib/sse` | `GET .../stream` | `message` y `current_asset` como texto | Playwright o test del parser + un stream real | verified |
| Keep-alive y reconexión | Ignora comentarios; `onerror` → polling 2 s | Igual | `ProgressBus` replay | No marcar `failed` solo porque cayó el socket | Test de parser; test de polling | verified |
| `aborted` vs `failed` | GET del run tras etapa SSE `failed` | Igual. No colapsar los dos | `RunStatusResponse.status` | No reclasificar leyendo `error_message` | Caso de fixture safety-abort si el e2e ya lo tiene; si no, unit del mapeo con JSON fixture | verified |
| Asset issues | `<details>` en `run.html` | Misma sección | `asset_issues` | `source_url` y `error_message` como texto; href vía `safeUrl` | RTL hostil | verified |
| Findings, filtros, orden del API | Tabla en `run.html` | `/v2/runs/[runId]` | `GET .../findings` | No reordenar por severidad calculada en cliente; `severity null` visible como unclassified | RTL + API | verified |
| Evidence | `x-text` | Nodo de texto | `evidence_snippet` | HTML del snippet no se interpreta | RTL con `<script>` | verified |
| Drawer del finding | `run.html` | Sheet | Campos de `FindingResponse` | Prosa LLM como texto; `reproduction_steps` como lista de texto | RTL | verified |
| Enlace al asset | `safeUrl()` | `lib/security/safeUrl` | `asset_source_url`, `asset_final_url` | Solo `http`/`https` | Unit de `safeUrl` | verified |
| Feedback | PUT/DELETE en el drawer | Igual | `/api/feedback/{id}` | CSRF; viewer no muta | Playwright rol operator y viewer | verified |
| Export md, json, html, csv, bounty | Enlaces en `run.html` | Mismos cinco | `GET .../export?format=` | `format` enum; `run_id` codificado | e2e de un formato + unit de la URL | verified |
| Dashboard | `dashboard.html` | `/v2/dashboard` | `GET /api/stats` | Números y etiquetas del API; sin KPIs nuevos | Comparar campos con la plantilla V1 antes de dar `verified` | verified |
| Historial y cursor | `history.html` | `/v2/runs` | `GET /api/runs` | Status como texto del enum, incluido `aborted` | Paginación | verified |
| Scopes CRUD | `scopes.html` | `/v2/scopes` | `/api/scopes` | CSRF; dominios como texto | e2e | verified |
| Import de scope | File input → POST body crudo | Igual, sin “mejorar” el JSON | `POST /api/scopes/import` | No evaluar el fichero; es texto/JSON | Fixture portable | verified |
| Login | `login.html` | `/v2/login` | `POST /api/auth/login` | CSRF pre-sesión; no guardar password | Playwright | verified |
| Register | `register.html`, 404 si auth off | Igual | `POST /api/auth/register` | Código de invitación como texto | Ambos modos de auth | verified |
| Setup | `setup.html` | `/v2/setup`. El formulario existe **y la página tiene el gate** (T9): `GET /api/auth/me` reporta `setup_available`; auth off → 404, ya provisionado → `/login`, API caída → el form se queda y el POST falla cerrado | `POST /api/auth/setup` | El token no va en el bundle. El POST sigue respondiendo 404 cuando el setup no aplica | Backend: `me` reporta la postura en ambas ramas; unit del helper | verified |
| Users e invitaciones | `users.html` | `/v2/users`. Alta, rol, borrado, invitación y revocación. El código se muestra una vez. Los 409 de “último operator” salen como HTTP genérico, no con el texto de V1 | `/api/users`, `/api/invitations` | Código de invitación una sola vez, texto; no `mailto:` automático | e2e operator | verified |
| Rol viewer | Mutaciones ocultas en parte; el API responde 403 | Ocultar controles y seguir manejando el 403 | `require_operator_action` | La UI no es la autoridad | Playwright viewer | verified |
| Auth desactivado | Sin redirect a login | Mismo modo, sin pantalla de login forzosa | Dependencies no-op | No inventar credenciales | e2e | verified |
| Health | `GET /api/health` | Puede usarlo el proxy; no hace falta página | `{status: ok}` | Público | Ya cubierto por pytest; repetir solo si el proxy lo usa | verified |

## CLI y backend que no son una pantalla V1

Estas filas no pueden desaparecer del producto, y tampoco se reimplementan en React.

| V1 Feature | V1 Implementation | V2 | API / nota | Seguridad | Test | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CLI `scan`, `show`, `report`, `list-runs`, `serve` | `cli/main.py` | No se migra | Mismo orquestador | Gates de scope en servidor | pytest CLI existente | out_of_scope |
| CLI `scope import/export` | `cli` + `scopes/portable.py` | Import sí está en la UI V1 (fila de arriba). Export de scope es CLI | `POST /api/scopes/import` ya usado; el export de fichero es CLI | Portable schema en servidor | pytest existente | out_of_scope |
| CLI `watch` | `services/watch.py` | Sin página | `watch: true` existe en `ScanRequest` y Web V2 de paridad no lo envía | Mismos gates que un scan | pytest watch | out_of_scope |
| CLI `kb` | `knowledge/portable.py` | Sin página | `/api/knowledge/*` | Import no ejecuta contenido | pytest knowledge | out_of_scope |
| Webhooks | `api/webhooks.py` | Sin página | CRUD JSON | Egress ya pasa por el guard en servidor; la UI futura no será quien decida el destino sin ese guard | pytest webhooks | out_of_scope |
| Pipeline, detectores, LLM, report builder | `src/metatracer/` | No se migra | — | Reglas inviolables | pytest actual | out_of_scope |

## Documentado en UI y no implementado en V1

No son deuda de paridad. Implementarlos en V2 sería feature nueva.

| Ítem | Dónde se menciona | En código | Estado |
| :--- | :--- | :--- | :--- |
| Breadcrumb History / target | `ui-architecture.md` §4 | No está en `run.html` | out_of_scope |
| Páginas Targets, Settings, AI, Reports | `ui-architecture.md` §3, marcadas “No hay página” | No hay ruta | out_of_scope |
| Cancelación cooperativa de scan | `tasks/06-interfaces.md` como nice-to-have | No hay endpoint | out_of_scope |
| `docs-agent-engineer` | Encargo de diseño V2 | No existe el agente | out_of_scope |

## Regresión prohibida

Una fila con implementación V1 (primera tabla) que pase a `missing` detiene el programa. No se compensa con una pantalla nueva de knowledge o de webhooks.
