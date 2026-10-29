# Mapa de componentes — MetaTracer

> **HISTÓRICO — no usar como contrato.** Mapea plantillas Jinja de la Web V1, retirada en
> T11 (ADR-0016). Las rutas `src/metatracer/api/templates/` y `static/` ya no existen.
> Mapa vigente: sección "Mapa de componentes reutilizables" de la propuesta de plataforma
> y los componentes en `web/src/components/`.

Cada plantilla actual → Keep / Refactor / Replace. No hay Replace de página: ninguna se tira ni se fusiona en una ruta nueva. “Refactor” significa markup y CSS, con el contrato Alpine y de red intacto.

Partials nuevos, opcionales, bajo `src/metatracer/api/templates/components/`. Solo si el JS de la página no se parte.

| Partial permitido | Qué contiene | Qué no contiene |
| :--- | :--- | :--- |
| `components/skip_link.html` | El `<a href="#main-content">` con el texto exacto | Lógica |
| `components/mark.html` | Palabra MetaTracer + `v{{ version }}` | Campana |
| No extraer | `scanWizard`, `runDashboard`, `safeUrl`, `trapFocus`, `MetaTracerUI` | — |

`MetaTracerUI` permanece en `base.html`. Los shells de auth no lo incluyen.

Clases visuales: las de `design-system.md`. Los nombres Alpine de la columna Estado son los actuales y se conservan.

## base.html — Refactor

- **Responsabilidad:** cromo de las páginas que extienden el layout, helpers JS, campana.
- **Datos:** contexto Jinja `version`, `auth_enabled`, `current_user` (`username`, `role`), `csrf_token`. Campana: `GET /api/notifications` → `{ total, notifications[] }` con `id, kind, run_id, target, total_assets, total_findings, error_message, created_at`. `kind` es `completed` | `failed`.
- **Estado:** `notifications_bell`: `open`, `entries`, `total`, `loadError`, `errorMessage`. Nuevo permitido: `navOpen` en un `x-data` de layout distinto del de la campana.
- **Interacción:** toggle de campana, refresh, dismiss `DELETE /api/notifications/{id}`, logout por `onclick`. Sidebar colapsada solo bajo 1024px.
- **Seguridad:** meta `csrf-token` condicional. `authFetch` / `logout` / redirect 401 sin cambios. Campana no se monta en auth. SVG inline, sin CDN de iconos. `x-text` para target y `error_message`.
- **Reutilización:** todas las páginas excepto login, register, setup.
- **No tocar:** el comentario de reglas (`|safe`, `x-html`), las URLs de CDN, el id `notifications-panel`, los aria de la campana, el texto del skip-link.

## index.html — Refactor (HIGH RISK)

- **Responsabilidad:** wizard de reconnaissance y gate de scope.
- **Datos:** `depths` desde el servidor. `GET /api/scopes`. POST `/api/runs` con `targets`, `scope_confirmed: true`, `reasoning_depth`, y una de `scope_ids` | `scope_domains`.
- **Estado:** `scanWizard`: `targets`, `scopeDomains`, `depth` default `standard`, `modalOpen`, `confirmed: false`, `starting`, `error`, `savedScopes`, `selectedScopeIds`, `lastFocused`.
- **Interacción:** validar → abrir modal → reset `confirmed` → foco en cancel → confirmar → POST → redirect o error. Escape cierra. Un scope guardado no salta el modal.
- **Seguridad:** el scope no se infiere del URL ni del target. Checkbox nunca `checked` en HTML ni en el init. `scope_confirmed` solo entra en el JSON dentro de `startScan` tras el guard `if (!this.confirmed) return`. Errores 409/403/404/429 con los textos actuales. Targets del modal vía `x-text`.
- **Reutilización:** no. El modal no se convierte en partial compartido en esta fase (el foco y los ids están atados al script).
- **Contrato de DOM que los tests fijan:** un solo `id="scope"` `type="text"` `x-model="scopeDomains"`; `id="scope-modal-cancel"`; `aria-labelledby="scope-modal-title"`; texto `Confirm authorized scope`. Se puede quitar `id="manual-scope"` al fusionar el campo duplicado, sin añadir un segundo `id="scope"`.
- **Foco:** entrada en Cancel, retorno a `lastFocused`, Escape. No añadir trampa de Tab (no existe hoy; añadirla cambia el comportamiento).

## run.html — Refactor (HIGH RISK)

- **Responsabilidad:** progreso, resultados, evidencia, análisis de IA, feedback, descargas.
- **Datos:**
  - Run: `RunStatusResponse` — `run_id, status, target, scope, reasoning_depth, total_assets, total_findings, error_message, started_at, completed_at, asset_issues[]` (`asset_id, source_url, status, skip_reason, error_message`).
  - SSE: `ProgressEvent`.
  - Findings: `FindingResponse` — `id, title, finding_type, type_label, severity` (nullable), `confidence, field_source, evidence_snippet, severity_justification, impact_analysis, remediation_advice, reproduction_steps, asset_source_url, asset_final_url, asset_content_type`.
  - Feedback: vote, `severity_after`, reason. No rediseñar el cálculo de `up`/`down`.
- **Estado:** `runDashboard` completo, incluidos `eventSource`, `pollTimer`, `stages`, filtros, `selected`, `trapFocus`, `safeUrl`.
- **Interacción:** no cambiar `init` (run id desde el path), `connectStream`, `handleEvent`, `startPolling`, `loadFindings`, `select` / `closeDrawer` / `trapFocus`, `copyEvidence`. Se puede mostrar `current_asset` y `current_step`/`total_steps` con `x-text` dentro de `handleEvent` **sin** alterar las ramas `completed` / `failed`.
- **Seguridad:** evidencia solo en `<pre x-text>`. URLs solo con `safeUrl`. Prosa del modelo en la zona “AI analysis — not evidence”, también `x-text`. Export: cinco `<a>` con `format` fijo y `download`. Sin `|safe`.
- **Reutilización:** badges vía clases `.mt-badge-*`. El drawer no se extrae a otro fichero en la fase 7.
- **Presentación nueva permitida:** panel si `status === 'aborted'` (solo `x-show`). No reclasificar `failed`. Asset issues visualmente distintos del banner de fallo. Cero findings neutro.

## dashboard.html — Refactor

- **Responsabilidad:** snapshot de `GET /api/stats`.
- **Datos:** únicamente `runs`, `assets`, `findings`, `top_domains`, `top_evidence`, `agent_usage` como en `DashboardStats`. Empty si `runs.total === 0`.
- **Estado:** `dashboard`: `stats`, `loadError`, `errorMessage`, `severityOrder`. Métodos `statusCount`, `severityCount`, `severityWidth`, `typeOptions`, `load`.
- **Interacción:** carga al init, Retry. Sin filtros nuevos ni drill-down (no hay endpoint de detalle).
- **Seguridad:** `evidence_snippet` con `truncate` + `x-text`. `domain` con `x-text`, no como `href`.
- **Reutilización:** `.mt-panel`, `.mt-kpi`, `.mt-badge`, barras por severidad.
- **Corrección visual obligatoria:** quitar el KPI que llama “Scope domains” a `top_domains.length`. La tabla “Top domains” se queda. Quitar el gradiente `.severity-bar`.

## history.html — Refactor

- **Responsabilidad:** `GET /api/runs` paginado.
- **Datos:** `RunListItem`: `run_id, status, target, scope, total_assets, total_findings, started_at, completed_at`. Paginación: `total`, `has_more`, `next_cursor`. `PAGE_LIMIT = 50`.
- **Estado:** `runHistory`. Filtros `all, completed, failed, running, pending, aborted`.
- **Interacción:** `setStatus`, `loadPrevious`, `loadNext`. El enlace de fila es `'/runs/' + run.run_id` (id de la API, no el target).
- **Seguridad:** target con `x-text`. No construir el href con el target.
- **Reutilización:** tabla y badges de estado. El `scope` del ítem puede mostrarse como metadata mono si cabe; si no cabe en móvil, queda fuera y se ve en el run. No es un dato nuevo.

## scopes.html — Refactor

- **Responsabilidad:** CRUD e import.
- **Datos:** `ScopeResponse`. Import: mensajes 413 y error 500 sin vaciar la lista. 409 si el nombre existe.
- **Estado:** `scopeManager`: `scopes`, `loaded`, `loadError`, `editing`, `form`, `importBusy`, `importMessage`, `importError`.
- **Interacción:** save, edit, cancel, delete, import file. Mutaciones vía `authFetch`.
- **Seguridad:** dominios son datos de operador, igualmente `x-text`. No `|safe`.
- **Reutilización:** `.mt-input`, `.mt-panel`, `.mt-table-wrap`, `.mt-alert-*`.
- **Copy de producto que se queda:** editar o borrar un scope no cambia runs pasados (el párrafo actual).

## users.html — Refactor

- **Responsabilidad:** administración operator.
- **Datos:** usuarios (`id, username, role, created_at`); invitaciones. `freshCode` solo desde el POST de creación.
- **Estado:** `users_admin`: `tab` `users|invitations`, `forbidden`, loads, `busy`, `actionError`, `freshCode`, `copied`.
- **Interacción:** tabs, crear, cambiar rol, borrar, crear invitación, copiar, revocar. Todo `authFetch`.
- **Seguridad:** el código en claro no va a un query string, ni a `localStorage`, ni al log de UI. Se pinta con `x-text`. Password `type="password"` `autocomplete="new-password"`. Mínimo 8 caracteres.
- **Reutilización:** tabs y tabla. El banner del código usa borde `--mt-border-strong`, texto `--mt-fg`, mono. No usar verde neón.

## login.html — Refactor

- **Responsabilidad:** `POST /api/auth/login`.
- **Datos:** username, password. Errores 401 y 429 ya ramificados en el script.
- **Estado:** `login_form`: `username`, `password`, `busy`, `error`.
- **Interacción:** submit, enlace a `/register` solo si `auth_enabled`.
- **Seguridad:** no extender `base.html`. CSRF: header desde `<meta name="csrf-token">` o cookie `csrf_token`, como ahora. No cargar la campana. Mismos dos `<script>` de CDN, versiones fijadas, más `metatracer.css`.
- **Reutilización:** clases `.mt-input`, `.mt-btn-primary`, `.mt-alert-danger`, `.mt-title`. Duplicar esas clases en el HTML standalone; no compartir el layout.

## register.html — Refactor

- Igual que login en stack y aislamiento.
- Campos: invitation `code`, `username`, `password`. Copy: `Create your account`, `Minimum 8 characters.`, enlace `Back to sign in`.
- Errores ya tratados: 401, 409, 422, 403. No unificar el texto si eso cambia el significado.
- 404 de servidor cuando auth está off: no dibujar un empty state para eso.

## setup.html — Refactor

- Igual aislamiento.
- Campos: `setup_token` (`type="password"`), `username`, `password`. Ayuda: el token de un solo uso sale en la consola del servidor.
- No mostrar el token en claro en un banner después del POST. No persistirlo en Alpine más allá del modelo del formulario.

## Piezas transversales

| Pieza | Decisión | Notas |
| :--- | :--- | :--- |
| Skip-link | Keep (mover a partial solo si el texto y el href quedan idénticos) | Tests |
| Campana | Refactor visual, Keep lógico | Sigue en `base.html` |
| Modal de scope | Refactor visual | Ids y foco intactos |
| Drawer | Refactor visual | `trapFocus` intacto |
| Tablas | Refactor | Misma semántica de columnas |
| Badges | Replace visual | De utilidades Tailwind sueltas a `.mt-badge-*` |
| `.severity-bar` | Replace | Barras por severidad, cuando el dashboard deje de usarla |
| Tailwind + Alpine | Replace (a `/static`) | TASK-26 opción A: CSS compilado y Alpine vendored; sin CDN de scripts |
| Auth shells | Refactor visual, Keep aislamiento | Prohibido `{% extends "base.html" %}` |

## Archivos que ui-engineer no modifica

- `src/metatracer/services/orchestrator.py`
- `src/metatracer/services/dashboard.py`
- `src/metatracer/api/schemas.py`
- `src/metatracer/api/pages.py`
- `src/metatracer/api/runs.py`
- `src/metatracer/cli/**`
- `src/metatracer/core/**`
- `src/metatracer/agents/**`
- `src/metatracer/db/**`
- `pyproject.toml`, `Dockerfile`, `.env.example`
- `.cursor/agents/ui-architect.md`
