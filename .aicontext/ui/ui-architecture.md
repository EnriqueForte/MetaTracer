# Arquitectura de UI — MetaTracer

Contrato para `ui-engineer`. Documentación en español. Identificadores, rutas, enums y cadenas de UI en inglés.

Este rediseño sustituye el planteamiento visual de TASK-26 (borrador 2026-09-19) en lo que el operador ha redefinido abajo. TASK-26 sigue siendo la deuda de **quitar el CDN**; eso no forma parte de este trabajo.

## 0. Decisiones cerradas

1. Stack: FastAPI + Jinja2 autoescape + Alpine.js 3.14.8 + Tailwind 3.4.16 (CDN ya fijado) + `metatracer.css`. Sin React, Next, Vite, Node ni bundlers.
2. Los CDN fijados se quedan. Las opciones A (Tailwind standalone CLI) y B (CSS a mano que reemplace Tailwind) de TASK-26 son **SUPPLY-CHAIN FOLLOW-UP** y exigen `safety-guardian`. Sin dependencias nuevas, sin CDN de fuentes, sin CDN de iconos, sin `@latest`, sin experimento SRI que rompa el play CDN de Tailwind.
3. No hay rutas ni features nuevas. La IA conceptual se apoya solo en páginas que ya existen (sección 3).
4. Comportamiento protegido: no cambiar `ScanOrchestratorService`, CLI, contratos request/response, forma SSE, scope gate, CSRF double-submit, autoescape, prohibición de `|safe` / `x-html` / `innerHTML` sobre datos del target, `safeUrl()` en `run.html`, un scan `running` → 409, fallo de asset continúa frente a fallo de safety que aborta, inglés de UI, skip-link, contrato de foco del modal de scope y del drawer (TASK-20).
5. La UI no calcula `severity`. Los enums viajan en minúsculas; Title Case solo en presentación.
6. Cabeceras CSP, `X-Frame-Options`, HSTS, `Referrer-Policy` y `Permissions-Policy` no existen hoy. **SECURITY FOLLOW-UP.** No diseñar un mecanismo de cabeceras que el backend no tiene.
7. No tocar `.cursor/agents/ui-architect.md`.

## 1. Current UI assessment

Superficie: `src/metatracer/api/templates/` + `src/metatracer/api/static/metatracer.css`. Las páginas HTML no interpolan hallazgos ni URLs del target: el shell Jinja pinta el marco y Alpine rellena con `x-text` desde la API.

| Plantilla | Ruta | Rol real |
| :--- | :--- | :--- |
| `base.html` | layout de páginas autenticadas o con auth off | Nav horizontal, campana, aviso ético, `window.MetaTracerUI`, skip-link |
| `index.html` | `GET /` | Wizard de scan + modal de scope |
| `run.html` | `GET /runs/{run_id}` | Progreso SSE, resultados, drawer, exports |
| `dashboard.html` | `GET /dashboard` | Agregados de `GET /api/stats` |
| `history.html` | `GET /runs` | Historial paginado |
| `scopes.html` | `GET /scopes` | CRUD e import de scopes |
| `users.html` | `GET /users` | Usuarios e invitaciones (operator) |
| `login.html` | `GET /login` | Shell standalone |
| `register.html` | `GET /register` | Shell standalone; 404 si auth off |
| `setup.html` | `GET /setup` | Shell standalone; 404 o redirect según gates de TASK-25 |

Problemas de UX (no de contrato):

- El esmeralda es a la vez acento, éxito, enlace, filtro activo y “no findings”. El color no discrimina.
- Paneles `bg-slate-900/60 border rounded-lg` repetidos. Densidad de SaaS, no de herramienta de inteligencia.
- `dashboard.html` pinta todas las severidades con `.severity-bar` (un gradiente). El cuarto KPI etiqueta `top_domains.length` como “Scope domains”; ese array tiene tope 10 (`_DASHBOARD_TOP_LIMIT`).
- `run.html` presenta `evidence_snippet` y la prosa del modelo con la misma jerarquía tipográfica.
- `index.html` enlaza dos inputs a `scopeDomains` (`id="scope"` y `id="manual-scope"`). El test `test_api_scope_scan_integration.py` exige `id="scope"` **exactamente una vez**.
- `run.status = aborted` se puede filtrar en historial, pero `_fail()` en el orquestador persiste el aborto de safety como `failed`. La UI no debe reclasificar `failed` leyendo `error_message`.

Lo que ya funciona y no se rediseña como comportamiento: modal bloqueante, checkbox no premarcado, SSE con fallback a polling, cero findings distinto de error de findings, `asset_issues` en `<details>`, cinco formatos de export, campana, CSRF, roles operator/viewer.

## 2. Current information architecture

Nav primaria (`base.html`), solo si la plantilla extiende `base.html`:

- New scan → `GET /`
- Dashboard → `GET /dashboard`
- History → `GET /runs`
- Scopes → `GET /scopes`
- Users → `GET /users` si auth está off, o si `current_user.role == 'operator'`

No hay breadcrumbs. El run se abre desde el historial (`/runs/{run_id}`) o por redirect tras el 202.

Auth no usa esa nav. Motivo en el comentario de `login.html`: la campana haría `GET /api/notifications` y un anónimo recibiría 401.

Datos que cada página ya consume:

| Página | Endpoint | Forma |
| :--- | :--- | :--- |
| `/` | `GET /api/scopes`, `POST /api/runs` | Scopes: `{ total, scopes[] }` con `id, name, description, domains, total_domains, created_at`. POST body: `targets`, `scope_confirmed: true`, `reasoning_depth`, y **exactamente una** fuente: `scope_domains` o `scope_ids` (el wizard no envía `scope_id` ni `watch`). 202 `{ run_id }`. 409, 403, 404, 429. |
| `/runs/{id}` | `GET /api/runs/{id}`, `GET .../stream`, `GET .../findings`, `GET .../export?format=`, `GET/PUT/DELETE /api/feedback/{id}` | Ver secciones 6 y 7. |
| `/dashboard` | `GET /api/stats` | `DashboardStatsResponse`. |
| `/runs` | `GET /api/runs` | `RunListResponse`: `total`, `runs[]`, `has_more`, `next_cursor`. |
| `/scopes` | `GET/POST /api/scopes`, `PUT/DELETE /api/scopes/{id}`, `POST /api/scopes/import` | |
| `/users` | `GET/POST /api/users`, `PATCH` rol, `DELETE`, invitaciones análogas | El código en claro solo existe en la respuesta de creación. |
| Auth | `POST /api/auth/login`, `/register`, `/setup`, `/logout` | CSRF previo a sesión, header `X-CSRF-Token`. |

## 3. Proposed information architecture

Mapa obligatorio. La columna “Conceptual” es la del diagrama del agente; la columna “Real” es la única implementación permitida.

| Conceptual | Real | Notas |
| :--- | :--- | :--- |
| Dashboard | `GET /dashboard` | Solo campos de `DashboardStatsResponse`. Empty state si `runs.total === 0`. Sin métricas inventadas. |
| Reconnaissance | `GET /` (`index.html`) | El wizard actual. Nav label: `Reconnaissance`. El botón de envío sigue siendo `Start scan`. |
| Targets | **No hay página** | El target es un campo del wizard, `run.target` y la columna del historial. |
| Results | `GET /runs/{run_id}` | Progreso, findings, asset issues y cabecera del run viven aquí. |
| Reports | **No hay página** | Descargas en el run, endpoint ya existente: `md`, `json`, `html`, `csv`, `bounty`. |
| History | `GET /runs` | |
| AI | **No hay página** | Campos del finding en el drawer del run, separados de `evidence_snippet`. |
| Settings | **No hay página** | |
| Scopes | `GET /scopes` | Ya existe; entra en la nav. No es “Targets”. |
| Users | `GET /users` | Operator. Misma condición Jinja de visibilidad. |

Preguntas que la UI debe poder responder con datos reales:

- Qué analizo: `run.target`, `run.scope`, `run.reasoning_depth` en el run; targets y scope en el modal antes de confirmar.
- Qué pasa: etapas SSE y `run.status`.
- Qué apareció: tabla de findings (`title`, `type_label`, `severity`, `evidence_snippet`, asset).
- Qué es sensible: orden ya viene del API (critical → info, unclassified al final). La UI no reordena por una severidad calculada en cliente.
- Qué evidencia lo sostiene: `evidence_snippet`, `field_source`, URLs y content-type.
- Qué concluye el modelo: `severity_justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps`.
- Qué investigar después: filtros ya existentes (severity, type, search) y el enlace al asset vía `safeUrl()`. Sin motor de “next steps” nuevo.

## 4. Navigation model

`base.html` pasa de header plano a layout con sidebar. Misma lista de enlaces, mismos `href`, mismo `aria-current="page"` cuando `request.url.path` coincide.

Orden de la sidebar:

1. Dashboard → `/dashboard`
2. Reconnaissance → `/`
3. History → `/runs`
4. Scopes → `/scopes`
5. Users → `/users` con la condición actual (`not auth_enabled` o role `operator`)

Cabecera contextual (no es una página nueva):

- Marca `MetaTracer` + `v{{ version }}` (el versionado ya está en el contexto de `pages.py`).
- Aviso ético, visible, no solo un icono. Texto actual, en inglés: “Authorized use only — audit exclusively targets you own or are explicitly authorized to test.”
- Campana: mismo `Alpine.data('notifications_bell')`, mismos `aria-expanded`, `aria-controls="notifications-panel"`, `aria-haspopup`.
- Si auth y hay usuario: “Signed in as {{ current_user.username }} ({{ current_user.role }})” y botón Sign out con `onclick="window.MetaTracerUI.logout()"` (no `@click` de Alpine: el botón está fuera del `x-data` de la campana).

No hay indicador de “system status” inventado. No hay poll nuevo para saber si hay un scan en curso fuera del run. La campana ya muestra notificaciones terminales (`completed` | `failed`).

Breadcrumb solo en el run, con datos ya cargados: `History` (`/runs`) / target (`x-text`, no href construido con el target). La página actual no es un enlace.

Auth shells no incluyen sidebar ni campana. Comparten clases visuales de `metatracer.css`, no `{% extends "base.html" %}`.

## 5. Main user flows

### 5.1 Reconnaissance → scan

1. El operador escribe targets (uno por línea) y elige **una** fuente de scope: scopes guardados (`selectedScopeIds`) o dominios manuales (`scopeDomains` en `id="scope"`).
2. Submit abre el modal. No hay POST todavía.
3. Al abrir: `this.confirmed = false`. El checkbox nace desmarcado. El foco va a `#scope-modal-cancel`.
4. Sin checkbox, el botón “Confirm and start scan” permanece `disabled`. `startScan()` retorna si `!this.confirmed`.
5. Solo entonces el body lleva `scope_confirmed: true` y **o** `scope_ids` **o** `scope_domains`. Nunca ambos. Nunca se rellena el scope parseando el target.
6. 202 → `location.assign('/runs/' + encodeURIComponent(data.run_id))`.
7. 409: “Another scan is already running; wait for it to finish.” 403: “The scope confirmation was rejected by the server.” Esos textos se conservan.

El modal sigue siendo un gate, no un aviso. Título estable para el test: `Confirm authorized scope` (`id="scope-modal-title"`).

Consolidación visual permitida en la fase 6: eliminar el input duplicado `id="manual-scope"` **solo si** queda un único `id="scope"` `type="text"` `x-model="scopeDomains"`. No cambiar la forma del POST.

### 5.2 Progreso

`ProgressEvent`: `run_id`, `stage`, `current_step`, `total_steps`, `message`, `current_asset` (opcional).

Etapas de trabajo, en este orden, ya en el array `stages` de `runDashboard`:

1. `scope_validation` — Scope validation
2. `discovery` — Discovery
3. `downloading` — Downloading
4. `extraction` — Metadata extraction
5. `detection` — Detection
6. `ai_analysis` — Classification and AI analysis
7. `report_generation` — Report generation

Terminales SSE: `completed`, `failed`. No son pasos del array. `total_steps` es 7.

La UI puede mostrar `current_step` / `total_steps`, `message` y, si viene, `current_asset`, siempre con `x-text`. No interpola porcentajes que el evento no trae. No anima un progreso inventado entre eventos.

### 5.3 Resultados, IA y reportes (misma página)

Cuando `run.status === 'completed'`: filtros, tabla, cero findings o error de findings, `asset_issues`, drawer, cinco enlaces de export.

La zona de reportes dice, en inglés, que la descarga regenera el archivo en el servidor (`GET /api/runs/{run_id}/export`) y que el navegador no archiva el reporte. Mostrar `run_id`, `target` y `completed_at` con `MetaTracerUI.formatWhen`. No inventar “generated at” distinto de `completed_at`.

Formatos y etiquetas (href ya existentes, `download`):

- Download Markdown — `format=md`
- Download JSON — `format=json`
- Download HTML — `format=html`
- Download CSV — `format=csv`
- Download Bounty TXT — `format=bounty`

Amenaza 10: el nombre del fichero lo pone el exporter. La UI no construye paths ni slugs.

### 5.4 Historial, scopes, usuarios

Sin cambios de flujo. Historial: filtros `all | completed | failed | running | pending | aborted`, página de 50, Newer / Older. Scopes: import JSON, alta/edición, delete; un 500 de import deja la lista. Users: tabs Users / Invitations; 403 muestra “Operator role required”; el código de invitación se muestra una vez desde la respuesta POST.

## 6. Layout architecture

Escritorio primero.

```
┌──────────────────────────────────────────────────────────┐
│ Skip link → #main-content                                │
├──────────────┬───────────────────────────────────────────┤
│ MetaTracer   │ Contextual: ethics, bell, account, sign out│
│ v{version}   ├───────────────────────────────────────────┤
│              │                                           │
│ Dashboard    │ <main id="main-content">                  │
│ Recon        │ {% block content %}                       │
│ History      │                                           │
│ Scopes       │                                           │
│ Users?       │                                           │
│              │                                           │
│ ethics line  │                                           │
│ (sidebar     │                                           │
│ footer)      │                                           │
└──────────────┴───────────────────────────────────────────┘
```

El aviso ético aparece en la cabecera en escritorio y, si no cabe, en el pie de la sidebar. No se elimina.

Auth:

```
        ┌─────────────────────┐
        │ Mark + page title   │
        │ form                │
        │ error alert         │
        └─────────────────────┘
```

`id="main-content"` se conserva en auth y en `base.html` (tests de skip-link y de users).

Overlay del modal de scope y del drawer: por encima del layout (`z-50` como ahora). El rediseño no los convierte en paneles inline: dejarían de ser bloqueantes.

## 7. Page hierarchy

### Dashboard

Empty (`runs.total === 0`): bloque “No data yet” y enlace a `/`. No pintar KPIs en cero como si fueran medición.

Con datos, solo estos campos:

- `runs.total` y `runs[status]` con fallback 0 si la clave falta (el contador del servicio solo incluye estados presentes).
- `findings.total`, `findings.unclassified`, `findings.severity_breakdown` (claves `critical|high|medium|low|info|unclassified`), `findings.by_type`.
- `assets.total`, `assets.with_issues`.
- `top_domains[]`: `{ domain, count }`, máximo 10. La etiqueta es “Top domains”, no un total de dominios de scope.
- `top_evidence[]`: `{ signature, evidence_snippet, finding_type, occurrences }`. `signature` es clave de lista, no se muestra como secreto ni se copia a un href.
- `agent_usage`: `calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms`. Se puede mostrar `total_tokens` (existe y hoy no se pinta). Ceros son válidos si no hubo `agent_log`.

Sin mapa de calor, sin tendencias, sin gráficos decorativos. La ruptura por severidad es una lista con etiqueta, cuenta y barra proporcional. El ancho sigue siendo un porcentaje numérico (`severityWidth`), nunca un string de CSS armado con datos del target.

### Reconnaissance

Una columna de formulario, ancho contenido (~40rem). Pasos visuales **dentro de la misma página**, no rutas:

1. Targets
2. Scope (guardados o manual; el manual no se infiere)
3. Reasoning depth (`brief|standard|detailed`, default `standard`, opciones ya inyectadas por `depths`)
4. Confirmación (el modal)

### Run

Orden vertical cuando el run existe:

1. Identidad: target, `run_id`, badge de `status`, `scope`, `reasoning_depth`, `total_assets`, `total_findings`, `started_at` / `completed_at`.
2. Un solo panel de estado terminal o de progreso (sección 8). No apilar el banner de fallo con la tabla de resultados.
3. Si `completed`: filtros, tabla, issues, reportes.
4. Drawer encima, no una tercera página.

### History, Scopes, Users

Tabla densa + barra de filtros o formulario encima. Users conserva `role="tablist"` y `aria-selected`.

## 8. Estados que no se mezclan

| Postura | Señal real | Tratamiento visual | Copy inglés (estable o nuevo, solo presentación) |
| :--- | :--- | :--- | :--- |
| Ready | Formulario de `/` sin `error` ni `starting` | Formulario en reposo | — |
| Starting | `starting === true` | Botón deshabilitado | `Starting scan…` |
| Running | `run.status` `pending` o `running` | Lista de etapas; la activa lleva texto “In progress”, no solo un spinner | `Progress` |
| Completed | `completed` y findings cargados con longitud > 0 | Tabla | badge `Completed` |
| Empty válido | `completed`, `findingsLoaded`, sin `findingsError`, `findings.length === 0` | Superficie neutra, no verde de éxito | `No findings` + “No sensitive metadata was identified in the {total_assets} asset(s) analyzed.” |
| Findings no cargables | `findingsError` no vacío | Alerta de error + el texto del helper | `Findings unavailable` |
| Filtro vacío | hay findings pero `filteredFindings.length === 0` | Fila de tabla | `No findings match the current filters.` |
| Safety u otro fallo terminal | `run.status === 'failed'` y `error_message` | Banner de fallo. **No** parsear el mensaje para decidir si fue safety. Hoy `_fail()` guarda `failed` tanto para `ScopeNotConfirmedError` / `SecurityViolationError` como para excepciones genéricas. | `Scan failed` + `error_message` vía `x-text` |
| Aborted (enum) | `run.status === 'aborted'` si la API lo devuelve | Badge y panel distintos del fallo genérico, mismo `error_message` si viene | `Scan aborted` |
| Asset fallido, run sigue | `run.asset_issues.length > 0` en un run que no está en el banner de `failed` (típicamente `completed`) | Bloque aparte, tono de aviso, no el rojo del run fallido | “Asset issues (…) — failed or skipped documents that did not abort the run” |
| Run desconocido | 404 o error de carga | `loadError` | `Run not found` o el mensaje HTTP ya usado |
| Dashboard vacío | `runs.total === 0` | Empty global | `No data yet` |
| Lista vacía | history / scopes / users | Empty propio de cada página | Textos ya presentes |

`aborted` en el historial ya tiene badge. No remapear filas `failed` a `aborted`.

No cambiar `connectStream`, `handleEvent` ni el predicado de `startPolling` (para en `completed` o `failed`). Un panel nuevo para `aborted` es solo presentación sobre `run.status`.

Estados de lista (TASK-20, se conservan): loading, empty, error con Retry, busy donde ya existe (`starting`, `importBusy`, SSE, `feedbackBusy`, `loadingMore`).

## 9. Responsive strategy

| Viewport | Sidebar | Tablas | Tabs (Users) | Formularios | Run / drawer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ≥1280px | Fija, 220px, siempre visible | Ancho del main, celdas mono con wrap en URLs | Tablist horizontal | Wizard a 40rem; scopes en una columna como ahora | Drawer `max-w-xl` desde la derecha |
| 1024–1279 | 200px | Igual; el main se reduce | Igual | Igual | Igual |
| 768–1023 | Colapsada. Botón `Menu` (`aria-expanded`, `aria-controls`) en la cabecera del layout. Al elegir un enlace, se cierra. No es una ruta nueva. | `overflow-x-auto` y caption `sr-only` ya existente | Tablist con wrap; no se convierten en un `<select>` que pierda `role="tab"` | Una columna, inputs al 100% | Drawer a ancho completo |
| <768 | Igual que tablet. El aviso ético queda en el pie de la sidebar abierta o bajo la marca, nunca `display:none` sin alternativa en el DOM. | Misma tabla con scroll horizontal, no cards que dupliquen columnas inventadas | Igual | Modal de scope: ancho completo con margen 1rem, sigue centrado y bloqueante | Drawer a viewport completo. Export en columna. Filtros en wrap, no un control nuevo |

El botón `Menu` es estado Alpine nuevo **en `base.html` solamente** (`navOpen`). No se copia a las páginas. En ≥1024px el botón no se muestra y el sidebar no depende de ese flag (CSS). Así un usuario de escritorio no queda sin nav si Alpine tarda.

Auth: una columna centrada en todos los anchos. Sin sidebar.

## 10. Accessibility strategy

La matriz de TASK-20 se revalida, no se reemplaza.

| Página | loading | empty | error 4xx/5xx | not-found | busy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/` | n/a (form estático) | n/a | `error`, incl. 409/403/429 | n/a | `starting` |
| `/runs/{id}` | loading run | zero findings ≠ `findingsError` | `loadError` + `findingsError` | run desconocido | SSE |
| `/runs` | sí | sí | sí + Retry | n/a | `loadingMore` |
| `/dashboard` | sí | global si `runs.total === 0` | sí + Retry | n/a | n/a |
| `/scopes` | sí | sí | sí + Retry + import 413/500 (la lista sigue) | n/a | `importBusy` |
| `base.html` campana | sí (al abrir refresca) | “No notifications yet.” | sí | n/a | n/a |
| `/login` `/register` `/setup` | n/a | n/a | `role="alert"` | gates de servidor (404 / redirect), no un empty de UI | `busy` |
| `/users` | por tab | “No users yet.” / “No invitations yet.” | sí + Retry; 403 “Operator role required” | n/a | `busy` |

Contrato de foco que no se altera:

- Skip-link: texto exacto `Skip to main content`, destino `#main-content`.
- Modal de scope: al abrir, foco en `#scope-modal-cancel`; al cerrar, foco de vuelta a `lastFocused`; Escape llama a `closeModal()`. `role="dialog"` `aria-modal="true"` `aria-labelledby="scope-modal-title"`. En el código actual el modal **no** tiene trampa de Tab (eso solo existe en el drawer). No añadir un ciclo de Tab en este rediseño: sería un cambio de comportamiento en una superficie HIGH RISK. No quitar entrada, retorno ni Escape.
- Drawer: foco inicial en el botón Close (`ref="drawerClose"`, `aria-label="Close finding details"`); `trapFocus` en Tab; retorno al disparador; Escape cierra. Filas: `tabindex="0"` y Enter llama a `select`.
- Campana: `aria-expanded` / `aria-controls` se mantienen.
- Severidad y estado nunca dependen solo del color: el badge incluye el texto Title Case.
- `aria-live="polite"` se queda donde ya está (cargas, import, `feedbackBusy`, paginación).
- Contraste: texto pequeño usa `--mt-fg` o `--mt-muted` sobre `--mt-bg` / `--mt-surface` con objetivo WCAG AA 4.5:1. `--mt-faint` no se usa para texto bajo 14px regular.
- `prefers-reduced-motion`: el spinner se sustituye por el texto “In progress” / “Loading…” sin animación. Ninguna animación de fondo.

## 11. Security constraints

Amenazas relevantes (`.agents/agents.md` §4.2):

- **10 — escritura fuera de `reports/`.** La UI no elige el path. Solo el query `format` ya permitido.
- **11 — bloque de evidencia.** `evidence_snippet` va en `<pre>` con `x-text` y `whitespace-pre-wrap`. No se reescriben backticks ni saltos. No se parte el snippet para “resaltar”.
- **12 — XSS.** Autoescape Jinja siempre. Prohibido `|safe`, `x-html` e `innerHTML` para datos del target, del modelo o de `error_message`. URLs de asset solo como `href` si `safeUrl()` las acepta (`^https?:\/\/`). Si no, `#`. `target="_blank"` conserva `rel="noopener noreferrer"`.
- **15 — cadena de suministro.** Únicas URLs de terceros, en `base.html` y en los tres shells de auth:

  - `https://cdn.tailwindcss.com/3.4.16`
  - `https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js`

  Iconos: el SVG de la campana ya está inline. Los nuevos iconos, si hacen falta, son SVG inline en la plantilla, sin red.

Datos del target y salida del modelo se tratan como no confiables. La prosa del LLM no es evidencia y no es HTML.

CSRF: meta `csrf-token` solo si hay token. Mutaciones por `MetaTracerUI.authFetch` (header `X-CSRF-Token` en POST/PUT/PATCH/DELETE; 401 → `/login` salvo si ya se está en `/login`). Login, register y setup no cargan `MetaTracerUI`; su `fetch` inline que lee el meta/cookie se conserva. No unificarlos con `base.html`.

Ética (feature 08): el producto es auditoría pasiva de documentos públicos autorizados. El modal conserva el párrafo de que no hay explotación y de que escanear sin autorización puede ser ilegal. No añadir “lab mode”, `--insecure`, ni un checkbox premarcado.

`scope_confirmed` solo pasa a `true` en el body después del confirm explícito. El valor inicial Alpine es `confirmed: false`.

Feedback de severidad (TASK-13) sigue siendo una corrección local del operador. No se presenta como evidencia ni como decisión del modelo. El voto lo calcula el JS actual; no rediseñar esa fórmula.

## 12. Technical constraints

- Alpine = UI state (modal, nav colapsada, tabs, filtros, drawer). La lógica de scan, scope, severidad y export permanece en servicios.
- Un `Alpine.data` por página, con los nombres actuales: `scanWizard`, `runDashboard`, `dashboard`, `runHistory`, `scopeManager`, `users_admin`, `notifications_bell`, `login_form`, `register_form`, `setup_form`.
- Helpers únicos: `MetaTracerUI.readError`, `truncate`, `formatWhen`, `authFetch`, `logout`, `csrfToken`. Las páginas delegan. No reintroducir copias.
- `pages.py` no cambia de plantilla ni de contexto (`version`, `auth_enabled`, `current_user`, `csrf_token`, `depths` en el index).
- El `run_id` de `run.html` se lee del path en el cliente, no se interpola en el script.
- Clases de layout Tailwind sí. Colores de marca y componentes, no: van a clases `.mt-*` para no duplicar `emerald-*` / `slate-*` con un significado distinto en cada página.
- El play CDN no recibe un `tailwind.config` nuevo en esta fase (evita un segundo mecanismo de tema). Los colores salen de variables CSS referenciadas por clases propias.
- Rendimiento: no añadir librerías, fuentes, ni un segundo stream. El sidebar es HTML estático. Partials Jinja que solo parten el markup, no el JS.

## 13. Fuera de este rediseño

- **SUPPLY-CHAIN FOLLOW-UP:** retirar CDN (TASK-26 opciones A o B). Requiere `safety-guardian`. Hasta entonces los tests no deben exigir ausencia del CDN.
- **SECURITY FOLLOW-UP:** cabeceras HTTP de seguridad. No hay middleware que las envíe. No diseñar nonces CSP ni SRI en plantillas “por si el backend aparece”.
- **REQUIRED BACKEND DATA (no bloquea el rediseño):** un discriminador explícito safety-abort frente a `failed` genérico. Mientras no exista, la UI muestra `failed` y `aborted` como estados distintos solo cuando el JSON trae ese `status`.
- No hay página Targets, Settings, AI ni Reports.
- No se añade el flag `watch` al wizard.
- No se migra a SPA. Si algún día se hace, es **FUTURE ARCHITECTURE OPTION**: la API ya está separada del HTML; el coste es reimplementar foco, CSRF, SSE y autoescape en un runtime Node que este repo no tiene. No forma parte del diseño actual.

## 14. Checklist de esta arquitectura

- [x] Nav real, sin Targets / Settings / AI / Reports como páginas
- [x] Flujo target → scope → confirmación → scan → progreso → resultados → análisis → descarga
- [x] Estados de fallo, asset y vacío separados, con la salvedad del status `failed` documentada
- [x] Compatible con FastAPI, Jinja2, Tailwind CDN fijado, Alpine, SSE
- [x] Scope sigue siendo un gate
- [x] Sin HTML inseguro propuesto
- [x] Orquestador, CLI, DB y contratos API fuera de alcance
