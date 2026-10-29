# Plan de rediseño — MetaTracer

> **HISTÓRICO — no usar como contrato.** Plan del rediseño de la Web V1 (Jinja + Alpine),
> retirada en T11 (ADR-0016). Contrato vigente: [`design-system-v2.md`](design-system-v2.md).

Implementación incremental. Cada fase: implementar → tests de `test-engineer` → revisión de
`safety-guardian` cuando la fase lo marca → seguir.

Ninguna fase cambia contratos de API, el orquestador, la CLI ni la forma de `ProgressEvent`.

El CDN ya no forma parte de la UI de destino: la opción A de TASK-26 (Tailwind compilado +
Alpine vendorizado en `/static`) se aplicó al cerrar el rediseño (2026-09-21) y se verificó en la
regresión final (ver "SUPPLY-CHAIN FOLLOW-UP" al final).

## Fase 0 — Tokens

- **Objetivo:** dejar el design system usable sin cambiar comportamiento.
- **Archivos:** `src/metatracer/api/static/metatracer.css` únicamente.
- **Componentes:** ninguno de plantilla. Añadir `:root`, `.mt-title`, `.mt-section`, `.mt-body`, `.mt-label`, `.mt-meta`, `.mt-tech`, `.mt-evidence`, `.mt-panel`, `.mt-kpi`, `.mt-btn-*`, `.mt-input`, `.mt-badge-*`, `.mt-alert-*`, `.mt-empty`, `.mt-loading`, `.mt-table-wrap`, `.mt-spin`, y la media query `prefers-reduced-motion`. Recolorear scrollbars. Conservar `[x-cloak]`. No borrar `.severity-bar` hasta la fase 3 (el dashboard aún la usa).
- **Riesgo:** LOW.
- **Dependencias:** ninguna.
- **Aceptación:** las páginas actuales se ven igual (las clases nuevas no están aplicadas). `x-cloak` sigue ocultando el markup previo a Alpine. No hay URLs nuevas en el CSS.
- **test-engineer:** smoke de que `/`, `/dashboard` y `/login` siguen renderizando. Un diff que solo toque `metatracer.css` y no las plantillas basta como evidencia.
- **safety-guardian:** amenaza 15, confirmar que el CSS no importa fuentes ni `@import` remotos.

## Fase 1 — Auth shells

- **Objetivo:** login, register y setup con el sistema visual, siguen standalone.
- **Archivos:** `login.html`, `register.html`, `setup.html`.
- **Componentes:** `.mt-panel`, `.mt-input`, `.mt-btn-primary`, `.mt-alert-danger`, `.mt-title`, `.mt-meta`.
- **Riesgo:** MEDIUM (CSRF y aislamiento del layout).
- **Dependencias:** fase 0.
- **Aceptación:**
  - No hay `{% extends "base.html" %}`.
  - No aparece `notifications_bell` ni `MetaTracerUI`.
  - Los assets de UI salen de `/static/tailwind.css` y `/static/alpine-csp-3.17.4.min.js`. No hay `<script src>` de terceros.
  - `id="main-content"` presente.
  - Campos, `autocomplete`, `type="password"` y ramificación de status HTTP sin cambios.
  - Enlace register solo si `auth_enabled`. Setup no revela el token fuera del input password.
- **test-engineer:** páginas de auth existentes; 401/429 de login; 404 de register con auth off; gates de setup.
- **safety-guardian:** amenaza 12 (x-text del error) y 15 (CDN sin cambios). CSRF pre-sesión: el header se sigue leyendo del meta o de la cookie `csrf_token`.

## Fase 2 — Layout global y navegación

- **Objetivo:** sidebar + cabecera en `base.html` sin cambiar destinos.
- **Archivos:** `base.html`. Partial opcional `components/skip_link.html` solo con el texto exacto `Skip to main content`.
- **Componentes:** nav, campana (solo piel), bloque de cuenta, `navOpen`.
- **Riesgo:** MEDIUM (logout, CSRF meta, skip-link, campana).
- **Dependencias:** fase 0. Puede ir en paralelo con la fase 1.
- **Aceptación:**
  - Enlaces: `/dashboard`, `/`, `/runs`, `/scopes`, y `/users` con la misma condición Jinja.
  - `aria-current="page"` se mantiene.
  - Labels visibles: `Dashboard`, `Reconnaissance`, `History`, `Scopes`, `Users`.
  - Skip-link intacto. `#main-content` intacto.
  - Campana: ids y aria intactos; `authFetch` intacto; Sign out sigue en `onclick="window.MetaTracerUI.logout()"`.
  - Aviso ético visible en DOM en todos los anchos.
  - CDN sin cambios. `MetaTracerUI` sin cambios de firma.
  - Por debajo de 1024px el botón `Menu` controla la sidebar y no tapa el foco del main cuando está cerrada.
- **test-engineer:** `test_a11y_focus.py` (skip-link, aria de campana); `test_user_pages.py` (skip-link y visibilidad de Users). Campana: empty, error, dismiss. Logout sigue posteando `/api/auth/logout` con CSRF.
- **safety-guardian:** amenaza 12 en los `x-text` de la campana. Amenaza 15. El session cookie no entra en el HTML.

## Fase 3 — Dashboard

- **Objetivo:** jerarquía de datos reales y severidad legible.
- **Archivos:** `dashboard.html`, y entonces sí borrar `.severity-bar` de `metatracer.css` si ya no hay referencias.
- **Componentes:** `.mt-kpi`, `.mt-panel`, `.mt-table-wrap`, badges de tipo, barras por severidad.
- **Riesgo:** LOW.
- **Dependencias:** fases 0 y 2.
- **Aceptación:**
  - Sigue un solo `GET /api/stats` en `load()`.
  - Empty cuando `runs.total === 0`, con `No data yet`, sin KPIs de relleno.
  - Con datos: runs, findings (total + unclassified), assets (total + with_issues), agent_usage (incluir `total_tokens`).
  - Tabla top domains etiquetada `Top domains`. No existe un KPI “Scope domains” basado en `.length`.
  - Tabla top evidence: snippet truncado, `finding_type` con el mapa de etiquetas, `occurrences`.
  - Cada severidad tiene etiqueta y color propios. Ancho = porcentaje numérico.
  - Loading, error + `Retry`, textos de vacío de las dos tablas.
- **test-engineer:** `test_dashboard_page.py` empty y error 500.
- **safety-guardian:** amenaza 11 y 12 sobre `evidence_snippet`. Amenaza 14: no ampliar el truncate ni pedir el campo completo.

## Fase 4 — History

- **Objetivo:** tabla densa y badges de estado alineados al design system.
- **Archivos:** `history.html`.
- **Componentes:** filtros `.mt-btn-secondary` con `aria-pressed`, tabla, empty, paginación.
- **Riesgo:** LOW.
- **Dependencias:** fases 0 y 2.
- **Aceptación:**
  - Filtros internos: `all`, `completed`, `failed`, `running`, `pending`, `aborted`.
  - Href de fila: `/runs/` + `run_id`.
  - Newer / Older, `Loading more…`, `PAGE_LIMIT` 50, uso de `next_cursor` sin cambios.
  - Empty `No runs yet`. Error + Retry.
  - Badge `Aborted` distinto de `Failed`.
- **test-engineer:** `test_history_page.py` empty y error. Paginación has_more. Filtro `aborted` no convierte filas `failed`.
- **safety-guardian:** amenaza 12 en `target` (x-text, href solo con run_id).

## Fase 5 — Scopes y Users

- **Objetivo:** formularios y tablas al sistema, mutaciones intactas.
- **Archivos:** `scopes.html`, `users.html`.
- **Componentes:** inputs, alerts, tabs, tabla, banner del código de invitación.
- **Riesgo:** MEDIUM (CSRF en todas las mutaciones; secreto de invitación).
- **Dependencias:** fases 0 y 2.
- **Aceptación:**
  - Scopes: import 413 muestra error; un fallo 500 no borra la lista en pantalla; `importBusy` deshabilita el botón; copy de “no cambia runs pasados” se mantiene.
  - El input file no usa `style=` inline.
  - Users: tabs con `aria-selected`; 403 “Operator role required”; `freshCode` solo tras crear; Copy sigue en el handler actual.
  - Passwords siguen en `type="password"`.
  - Todas las mutaciones siguen en `authFetch`.
- **test-engineer:** `test_scopes_page.py` (empty, error, 413). Tests de users: 403 viewer, creación, banner del código no presente en el GET inicial.
- **safety-guardian:** amenaza 12. El código de invitación no se interpola en Jinja ni se mete en una URL. CSRF en POST/PUT/DELETE.

## Fase 6 — Reconnaissance (HIGH RISK)

- **Objetivo:** jerarquía visual del wizard y del modal, sin mover el gate.
- **Archivos:** `index.html` solamente.
- **Componentes:** formulario `.mt-panel`, modal, alerta de error. No extraer el modal a un partial.
- **Riesgo:** **HIGH RISK.** Toca el modal de scope.
- **Dependencias:** fases 0 y 2. No empezar en paralelo con la fase 7.
- **Aceptación:**
  - `confirmed: false` en el estado inicial y `this.confirmed = false` al abrir el modal.
  - El checkbox no tiene atributo `checked`.
  - El botón de confirmar sigue `:disabled="!confirmed || starting"`.
  - `startScan` sigue retornando si `!this.confirmed`.
  - Body POST: `scope_ids` **o** `scope_domains`, nunca los dos, nunca `scope_confirmed` antes de esa función, nunca `watch`.
  - Textos de validación, 409 y 403 idénticos a los actuales.
  - DOM de test: exactamente un `id="scope"` con `type="text"` y `x-model="scopeDomains"`; `scope-modal-cancel`; `scope-modal-title`; texto `Confirm authorized scope`.
  - Foco: `$nextTick` → `#scope-modal-cancel`; cierre restaura `lastFocused`; Escape → `closeModal()`. Sin trampa de Tab nueva.
  - Un fallo de `GET /api/scopes` no bloquea el flujo manual.
  - El párrafo legal/ético del modal se conserva en sustancia.
  - Pasos visuales 1–4 son headings dentro de la misma vista, no rutas.
- **test-engineer:** `test_a11y_focus.py`; `test_api_scope.py`; `test_api_scope_scan_integration.py` (un solo `id="scope"`). Flujo: sin checkbox el botón no envía; con checkbox, 202 redirige; 409 y 403 pintan `role="alert"`.
- **safety-guardian:** reglas de scope. Amenaza 12 en la lista de targets del modal. Prohibido `|safe` y `x-html`.

## Fase 7 — Run: progreso, resultados, IA, reportes (HIGH RISK)

- **Objetivo:** lectura de evidencia distinta del análisis del modelo, estados de run distinguibles, descargas claras.
- **Archivos:** `run.html` solamente.
- **Componentes:** etapas, banners, tabla, drawer en tres zonas, fila de exports. No partir el `Alpine.data`.
- **Riesgo:** **HIGH RISK.** Toca SSE y el render de evidencia.
- **Dependencias:** fases 0 y 2. Después de la fase 6.
- **Aceptación:**
  - `connectStream`, `handleEvent` (ramas `completed` y `failed`), `closeStream`, `startPolling` (sigue parando solo en `completed` o `failed`), `loadFindings`, `safeUrl`, `trapFocus`, `select`, `closeDrawer` conservan su lógica.
  - Se puede pintar `event.message`, y si se desea `event.current_asset` y `current_step`/`total_steps`, solo con `x-text`.
  - Etapas: las siete claves actuales, en el mismo orden, con las mismas labels inglesas.
  - `failed`: banner `Scan failed` + `error_message`. No inspeccionar el texto para decir “safety”.
  - `aborted`: panel propio `Scan aborted` si el status viene así. No remapear `failed`.
  - `asset_issues`: bloque distinto, copy actual de “did not abort the run”.
  - Cero findings ≠ `findingsError`. Cero findings no usa estilo de éxito.
  - Filtros y búsqueda conservan los campos que ya comparan.
  - Filas: `tabindex="0"`, Enter → `select`.
  - Drawer: `role="dialog"` `aria-modal="true"` `aria-labelledby="finding-drawer-title"`; foco al close; Tab cicla; Escape cierra; retorno al disparador.
  - Zona Evidence: solo snippet, field, URLs, content-type, Copy.
  - Zona con el rótulo exacto `AI analysis — not evidence`: justification, impact, reproduction steps, remediation.
  - Feedback debajo, fuera de las dos zonas. Misma API.
  - Cinco enlaces de export con los mismos `format`. Copy de que el archivo se regenera en el servidor. `completed_at` vía `formatWhen`.
  - `safeUrl` sin cambios: solo `http:` / `https:`; cualquier otro valor es `#`. Se conserva `rel="noopener noreferrer"`.
  - Evidencia en `<pre>` con `x-text` y `whitespace-pre-wrap`. Prohibido `|safe`, `x-html` e `innerHTML`.
  - La UI no asigna ni recalcula `severity`. El badge es Title Case; el filtro compara la clave en minúsculas.
  - `reproduction_steps` sigue siendo una `<ol>` de `x-text`.
- **test-engineer:**
  - Run 404 → `Run not found`.
  - Findings HTTP 500 → `findingsError` visible y distinto del empty.
  - `completed` + lista vacía → `No findings`, sin alerta de error.
  - `completed` + `asset_issues.length > 0` → el bloque de issues visible y el banner `Scan failed` oculto.
  - `failed` → banner `Scan failed` y `error_message`; la tabla de resultados no se muestra.
  - `aborted` (si el fixture lo trae) → copy `Scan aborted`, no `Scan failed`.
  - SSE: un evento `stage=downloading` marca esa etapa activa; `completed` cierra el stream y carga findings; `failed` cierra el stream y refresca el run.
  - Drawer: foco en Close, Tab no sale del diálogo, Escape devuelve el foco a la fila.
  - `safeUrl('javascript:alert(1)')` no es un enlace navegable.
  - Los cinco `format=` siguen en el HTML.
  - El rótulo `AI analysis — not evidence` está en el drawer y `evidence_snippet` no cae dentro de ese contenedor.
- **safety-guardian:** amenazas 10, 11, 12 y 14. Confirmar que el fallback a polling no abre un segundo `EventSource`.

## Fase 8 — Responsive

- **Objetivo:** la arquitectura de layout cambia por breakpoint, no solo se encoge.
- **Archivos:** `base.html` y ajustes de utilidad en las páginas ya migradas. Auth ya es una columna.
- **Riesgo:** MEDIUM. Si un cambio mueve `#scope-modal-cancel`, el foco o `trapFocus`, parar y tratarlo como HIGH RISK.
- **Dependencias:** fases 2 a 7.
- **Aceptación:**
  - ≥1024px: sidebar visible sin depender de `navOpen`.
  - <1024px: sidebar cerrada por defecto; `Menu` tiene `aria-expanded` y `aria-controls`; elegir un enlace la cierra.
  - El aviso ético sigue en el DOM.
  - Tablas conservan `<caption class="sr-only">` y hacen scroll horizontal.
  - Users conserva `role="tablist"`.
  - Modal de scope sigue centrado, bloqueante, con el mismo foco.
  - Drawer bajo 768px ocupa el ancho, conserva `trapFocus`.
- **test-engineer:** pasada a 1280px y 390px sobre las rutas reales.
- **safety-guardian:** el menú colapsado no duplica formularios ni un segundo `POST /api/runs`.

## Fase 9 — Regresión de accesibilidad y QA

- **Objetivo:** revalidar la matriz de TASK-20 sobre el DOM nuevo.
- **Archivos:** solo los que fallen un criterio. Sin barrido cosmético.
- **Riesgo:** LOW si no se toca `index.html` ni `run.html`. Si el fallo está en el modal o en el drawer, el arreglo se marca **HIGH RISK**.
- **Dependencias:** fases 1 a 8.
- **Aceptación:** matriz TASK-20 cubierta; skip-link `Skip to main content`; contraste AA; badges con texto; `prefers-reduced-motion`; inglés de UI; CDN fijados sin cambios.
- **test-engineer:** `test_a11y_focus.py`, `test_history_page.py`, `test_scopes_page.py`, `test_dashboard_page.py`, `test_user_pages.py`, `test_feedback_page.py`, `test_api_scope.py`, `test_api_scope_scan_integration.py`. Suite `pytest -m "not e2e"`, `ruff check src tests`, cobertura ≥85%. Adaptar selectores solo cuando el texto visible haya cambiado a propósito (nav `Reconnaissance`); no relajar aserciones de `id="scope"`, `scope-modal-cancel`, `Confirm authorized scope` ni del skip-link.
- **safety-guardian:** pase final de amenazas 10, 11, 12 y 15. Veto si aparece `|safe`, `x-html`, `innerHTML`, un CDN nuevo, una fuente remota, un `href` de asset sin `safeUrl`, o un `scope_confirmed` que no salga de `startScan` tras el checkbox.

## Seguimientos (no son fases de ui-engineer)

### SUPPLY-CHAIN FOLLOW-UP

**Cerrado (2026-09-21).** Opción A aplicada: Tailwind CSS 3.4.16 compilado offline a
`static/tailwind.css` (CLI oficial `tailwindcss-windows-x64.exe`, hash en TASK-26; el binario no
se versiona, no entra en Docker y la app no lo descarga) y Alpine servido desde
`static/alpine-csp-3.17.4.min.js` (build `@alpinejs/csp` 3.17.4, sin `unsafe-eval`). No queda
ningún `<script src>` de terceros en las plantillas; la regresión final (`pytest` 675 passed,
5 skipped, ruff limpio y revisión de `safety-guardian` sin bloqueantes) lo verificó.

### SECURITY FOLLOW-UP

Las cabeceras de respuesta las envía `api/security_headers.py`. Una CSP sin `'unsafe-inline'` sigue fuera.

### REQUIRED BACKEND DATA

Un campo que distinga aborto de safety frente a `failed` genérico no existe: `_fail()` persiste ambos como `failed`. La UI no lo infiere leyendo `error_message`.

## Archivos que no entran en ninguna fase

- `src/metatracer/services/orchestrator.py`
- `src/metatracer/services/dashboard.py`
- `src/metatracer/api/schemas.py`, `pages.py`, `runs.py`
- `src/metatracer/cli/**`, `core/**`, `agents/**`, `db/**`
- `pyproject.toml`, Dockerfile, `.env.example`
- `.cursor/agents/ui-architect.md`

## Orden de parada

Si una fase rompe el scope gate, el SSE, el 409, el CSRF, `safeUrl` o la separación evidencia/IA, no se continúa. Se revierte el comportamiento (el CSS puede quedarse) y se vuelve a marcar la fase como HIGH RISK.
