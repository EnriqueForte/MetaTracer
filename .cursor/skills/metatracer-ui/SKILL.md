---
name: metatracer-ui
description: Design system y stack real de la Web UI de MetaTracer — tokens y clases .mt-* de metatracer.css, Tailwind 3.4.16 compilado offline y Alpine CSP 3.17.4 vendorizados en /static (sin CDN), sidebar y layout por breakpoint, matrices de estado de TASK-20, renderizado seguro (autoescape, safeUrl, prohibición de x-html/|safe), cabeceras de seguridad de api/security_headers.py y paridad CLI/UI. Usar al trabajar en api/, cli/, services/, templates o static, y al implementar o revisar cualquier cambio de la Web UI (TASK-06, TASK-20, TASK-24/25, TASK-26).
---

# UI de MetaTracer — design system, stack y seguridad

Cubre las amenazas 10, 11, 12 y 15 del modelo de amenazas ([.agents/agents.md](../.agents/agents.md)).
Fuentes de verdad: `.aicontext/tasks/06-interfaces.md`, `20-ui-polish.md`, `26-ui-redesign.md` y
los contratos de `.aicontext/ui/` (`ui-architecture.md`, `design-system.md`,
`component-map.md`, `redesign-plan.md`).

**Principio:** la UI es donde el safety se hace visible y donde el contenido del target se
renderiza. El autoescape y la ausencia de CDN son tan inviolables como el wrapper HTTP.

## Stack real (tras TASK-26)

- Jinja2 con autoescape (Starlette default) + Alpine CSP 3.17.4 vendorizado
  (`static/alpine-csp-3.17.4.min.js`) + Tailwind 3.4.16 **compilado offline**
  (`static/tailwind.css`) + design system propio `static/metatracer.css`.
- **Cero scripts de terceros en runtime.** Sin CDN, sin fuentes, sin iconos remotos (SVG
  inline). Build de Alpine: el normal usa `new AsyncFunction` (CSP lo bloquea sin
  `unsafe-eval`); el build CSP de 3.14.8 solo acepta nombres de propiedad; 3.17.4 interpreta
  las expresiones actuales sin `eval`. No añadir `unsafe-eval`.
- Cabeceras de respuesta en `api/security_headers.py`: CSP con `'unsafe-inline'` (scripts
  inline, `onclick` de Sign out, estilos), sin orígenes de terceros, sin `unsafe-eval`;
  `frame-ancestors 'none'`; HSTS solo si HTTPS y no-local (mismo corte que la cookie `Secure`,
  `X-Forwarded-Proto: https`).
- Paridad: CLI y Web UI leen el mismo `ScanOrchestratorService` y muestran lo mismo para el
  mismo `run_id`.

## Design system (`.mt-*` en metatracer.css)

- **Tokens en `:root`:** superficies (`--mt-bg/surface/elevated/overlay`), líneas y texto
  (`--mt-border/-strong`, `--mt-fg/muted/faint`), acento acero (`--mt-accent`), feedback de
  producto (`--mt-danger/warning/success` + fondos y bordes), severidad
  (`--mt-sev-critical/high/medium/low/info/unclassified` + fondos), fuentes, escala de
  espacio (4px), radios (`--mt-radius-sm: 2px`, `--mt-radius-md: 4px`), sombra solo para
  modal/drawer.
- **Severidad.** El dato viaja en minúsculas; el badge muestra Title Case. `null` se presenta
  como `Unclassified` (no es un valor del enum). Critical rojo apagado, High cobre, Medium
  ámbar, Low azul acero, Info gris, Unclassified outline. El color nunca es el único canal:
  siempre hay texto.
- **Estados de run** (no severidad): `pending|running|completed|failed|aborted` con badges
  propios. `completed` no usa el color del botón primario.
- **Componentes:** `.mt-panel`, `.mt-kpi`, `.mt-table-wrap`, `.mt-btn-primary/secondary/
  danger/ghost`, `.mt-input`, `.mt-badge-*`, `.mt-alert-danger/warning/neutral/status`,
  `.mt-empty`, `.mt-loading`, `.mt-title`, `.mt-section`, `.mt-body`, `.mt-label`,
  `.mt-meta`, `.mt-tech`, `.mt-evidence`, `.mt-skip`. Tailwind queda para layout (`flex`,
  `grid`, `gap`, `min-w-0`, `overflow-x-auto`, `sr-only`, `contents`); nada de `emerald-*`
  como acento de producto ni clases ad-hoc por página.
- **Tipografía:** sin CDN de fuentes; mono para evidencia, ids, URLs y timestamps.

## Renderizado de datos del target (no confiables)

- Autoescape de Jinja2 siempre activo. **Prohibido** `|safe`, `x-html` e `innerHTML` sobre
  snippets, URLs, nombres de archivo, `error_message` o salida del modelo.
- Evidencia: `<pre>` con `x-text` y `whitespace-pre-wrap`, byte a byte igual a lo persistido.
  No reescribir backticks ni saltos; no partir el snippet para "resaltar".
- URLs de asset solo como `href` si `safeUrl()` las acepta (`^https?://`); si no, `#`;
  `target="_blank"` conserva `rel="noopener noreferrer"`.
- Separación visual obligatoria: `Evidence` (datos técnicos) vs `AI analysis — not evidence`
  (justificación, impacto, repro, remediación del modelo). El feedback de severidad (TASK-13)
  vive fuera de ambas zonas y no presenta la corrección local como decisión del modelo.

## Estados que no se mezclan (TASK-20)

| Postura | Señal real | Tratamiento |
| :--- | :--- | :--- |
| Ready / Starting / Running | `starting` / `run.status` | formulario en reposo; botón deshabilitado; lista de etapas con “In progress” |
| Completed | `completed` + findings cargados | tabla + badge `Completed` |
| Empty válido | `completed`, sin `findingsError`, `findings.length === 0` | superficie **neutra**, `No findings`; nunca estilo de éxito |
| Findings no cargables | `findingsError` | alerta + texto del helper |
| Filtro vacío | hay findings, `filteredFindings.length === 0` | `No findings match the current filters.` |
| Safety u otro fallo terminal | `run.status === 'failed'` + `error_message` | banner `Scan failed` (no parsear `error_message` para reclasificar) |
| Aborted | `run.status === 'aborted'` | panel `Scan aborted` distinto del fallo genérico |
| Asset fallido, run sigue | `run.asset_issues.length > 0` en run no `failed` | bloque aparte de aviso, no el rojo del run fallido |

`run.status` es la única fuente de verdad del estado; la UI **nunca** reclasifica `failed`
leyendo `error_message`. El progreso SSE se pinta con `x-text` de `ProgressEvent`
(`stage`, `current_step`/`total_steps`=7, `message`, `current_asset` opcional); no inventar
porcentajes ni animar progreso entre eventos. `connectStream`, `handleEvent` y `startPolling`
(solo para en `completed`/`failed`) no cambian.

## Contratos de foco y a11y

- Skip-link: texto exacto `Skip to main content` → `#main-content`.
- Modal de scope: al abrir, foco en `#scope-modal-cancel`; retorno a `lastFocused`; Escape →
  `closeModal()`; `role="dialog" aria-modal="true" aria-labelledby="scope-modal-title"`.
  **Sin trampa de Tab** (no existe hoy; añadirla es un cambio HIGH RISK).
- Drawer: foco inicial en Close (`ref="drawerClose"`), `trapFocus` en Tab, retorno al
  disparador, Escape cierra. Filas con `tabindex="0"` y Enter → `select`.
- Campana: `aria-expanded`/`aria-controls` intactos; no se monta en páginas de auth.
- Contraste AA 4.5:1; `--mt-faint` no para texto <14px regular; `prefers-reduced-motion`
  anula transiciones y spinner.
- Un `Alpine.data` por página: `scanWizard`, `runDashboard`, `dashboard`, `runHistory`,
  `scopeManager`, `users_admin`, `notifications_bell`, `login_form`, `register_form`,
  `setup_form`, `appShell` (layout). Helpers únicos en `MetaTracerUI`: `readError`,
  `truncate`, `formatWhen`, `authFetch`, `logout`, `csrfToken`.

## Auth (TASK-24/25)

- Cookie `HttpOnly` + CSRF double-submit (`X-CSRF-Token`); roles `operator`/`viewer`;
  kill-switch `METATRACER_AUTH_ENABLED` (default `false`). CLI sin login (postura documentada).
- `login.html`, `register.html`, `setup.html` son **standalone**: no extienden `base.html`,
  no cargan la campana ni `MetaTracerUI`; su fetch inline lee el meta/cookie CSRF pre-sesión.
- Rutas con auth: la nav de `base.html` muestra `Users` solo si auth off o rol operator.

## Checklist de revisión

- [ ] Ninguna plantilla referencia CDN de Tailwind, Alpine ni fuentes/iconos remotos.
- [ ] Sin `|safe`, `x-html` ni `innerHTML` sobre datos del target o salida del modelo.
- [ ] `safeUrl()` protege todo `href` de asset; `rel="noopener noreferrer"` en `_blank`.
- [ ] `run.status` dicta el estado; no se remapean `failed` → `aborted`.
- [ ] Scope gate intacto: checkbox nunca `checked`, `scope_confirmed` solo tras confirmar,
  `scope_ids` **o** `scope_domains` (nunca ambos), 409/403 con los textos estables.
- [ ] Drawer: evidencia y `AI analysis — not evidence` en zonas separadas.
- [ ] Estados de TASK-20 por página (loading/empty/error/busy) y foco de modal/drawer intactos.
- [ ] CSRF en todas las mutaciones; logout sin Alpine `@click` (botón fuera del `x-data`).