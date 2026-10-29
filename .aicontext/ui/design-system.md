# Design system — MetaTracer

> **HISTÓRICO — no usar como contrato.** Describe la Web V1 (FastAPI + Jinja2 + Alpine),
> retirada en T11 (ADR-0016). `src/metatracer/api/static/metatracer.css` y
> `src/metatracer/api/templates/` ya no existen.
> Contrato vigente: [`design-system-v2.md`](design-system-v2.md) e implementación en
> `web/src/app/globals.css`.

Contrato visual para `ui-engineer`. Implementación: custom properties y clases de componente en `src/metatracer/api/static/metatracer.css`. Tailwind 3.4.16 permanece para layout (`flex`, `grid`, `gap`, `min-w-0`, `overflow-x-auto`, `sr-only`, `contents`). No añadir `tailwind.config` en página. No usar `emerald-*` como acento de producto.

Las cadenas de UI de este documento están en inglés. Los comentarios del CSS pueden ir en español.

## 1. Design principles

1. Precisión sobre decoración. Cada bloque responde a un dato o a una acción que ya existe.
2. Evidencia sobre ruido. Lo que el extractor encontró se lee antes que lo que el modelo opina.
3. Un significado por color. El acero es acción/foco. El verde salvia es “completed”, no el CTA. La severidad tiene escala propia.
4. Densidad alta, cromo bajo. Bordes de 1px. Casi sin sombra. Radios pequeños.
5. El color no es el único canal. Badges de severidad y de estado llevan texto.
6. Movimiento solo al cambiar de estado.

Dirección: dark, technical, premium, minimal, security intelligence.

Prohibido en este sistema: cyberpunk, matrix, verde neón dominante, glassmorphism (`backdrop-blur` como estilo de panel), gradientes decorativos, partículas, gráficos sin dato, tarjetas SaaS con sombra suave y radio grande.

## 2. Color tokens

Añadir a `metatracer.css` dentro de `:root`. El hex es normativo. Si un par texto/fondo no llega a WCAG AA 4.5:1, se aclara el token de texto; no se vuelve al esmeralda.

```css
:root {
  /* surfaces */
  --mt-bg: #0C1014;
  --mt-surface: #141A20;
  --mt-elevated: #1B232C;
  --mt-overlay: rgba(12, 16, 20, 0.86);

  /* lines and text */
  --mt-border: #2C3642;
  --mt-border-strong: #3D4A59;
  --mt-fg: #E7EAED;
  --mt-muted: #A7B0BA; /* texto secundario ≥14px y labels 12px semibold */
  --mt-faint: #8B97A3; /* solo metadata ≥14px; no body 12px regular */

  /* accent: acero. No es severidad ni éxito. */
  --mt-accent: #6E8AA3;
  --mt-accent-hover: #8AA6BE;
  --mt-accent-fg: #0C1014;
  --mt-focus: #C5D4E2;

  /* feedback de producto, distinto de la escala de findings */
  --mt-danger: #E7B4B4;
  --mt-danger-bg: #2A1717;
  --mt-danger-border: #6B3030;
  --mt-warning: #E4D2A4;
  --mt-warning-bg: #2A2416;
  --mt-warning-border: #6B5A30;
  --mt-success: #C5D4C8;
  --mt-success-bg: #17211A;
  --mt-success-border: #3D5344;

  /* severity — cada una con fondo propio; el texto del badge es --mt-fg o el token */
  --mt-sev-critical: #E7B4B4;
  --mt-sev-critical-bg: #3A1C1C;
  --mt-sev-high: #F0C2A0;
  --mt-sev-high-bg: #3A2818;
  --mt-sev-medium: #E7D7A4;
  --mt-sev-medium-bg: #332E18;
  --mt-sev-low: #C5D5E0;
  --mt-sev-low-bg: #1A2832;
  --mt-sev-info: #C5CDD4;
  --mt-sev-info-bg: #22282E;
  --mt-sev-unclassified: #A7B0BA;
  --mt-sev-unclassified-bg: #1B232C;

  --mt-font-sans: ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  --mt-font-mono: ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;

  --mt-space-1: 4px;
  --mt-space-2: 8px;
  --mt-space-3: 12px;
  --mt-space-4: 16px;
  --mt-space-5: 24px;
  --mt-space-6: 32px;
  --mt-space-7: 48px;

  --mt-radius-0: 0;
  --mt-radius-sm: 2px;
  --mt-radius-md: 4px;

  --mt-shadow-overlay: 0 16px 40px rgba(0, 0, 0, 0.45);
}
```

El overlay del modal puede usar `--mt-overlay`. No usar desenfoque de fondo.

### Escala de severidad (presentación)

El dato sigue en minúsculas. El badge muestra Title Case. `null` se presenta como Unclassified; no es un valor del enum `severity`.

| Dato | Etiqueta visible | Fondo | Texto |
| :--- | :--- | :--- | :--- |
| `critical` | Critical | `--mt-sev-critical-bg` | `--mt-sev-critical` |
| `high` | High | `--mt-sev-high-bg` | `--mt-sev-high` |
| `medium` | Medium | `--mt-sev-medium-bg` | `--mt-sev-medium` |
| `low` | Low | `--mt-sev-low-bg` | `--mt-sev-low` |
| `info` | Info | `--mt-sev-info-bg` | `--mt-sev-info` |
| `null` / ausente | Unclassified | `--mt-sev-unclassified-bg` | `--mt-sev-unclassified` |

Critical es rojo apagado. High es cobre, no magenta. Medium es ámbar. Low es azul acero oscuro, no cian neón. Info es gris. Unclassified es outline, sin relleno saturado.

### Estado de run (no es severidad)

| Dato | Etiqueta | Tratamiento |
| :--- | :--- | :--- |
| `pending` | Pending | borde `--mt-border-strong`, texto `--mt-muted` |
| `running` | Running | borde `--mt-accent`, texto `--mt-accent-hover` |
| `completed` | Completed | fondo `--mt-success-bg`, texto `--mt-success` |
| `failed` | Failed | fondo `--mt-danger-bg`, texto `--mt-danger` |
| `aborted` | Aborted | fondo `--mt-warning-bg`, texto `--mt-warning` |

Completed no usa el color del botón primario.

### Confianza

`high` | `medium` | `low` → etiquetas High / Medium / Low con prefijo visible `Confidence`. Estilo neutro (borde), no la escala de severidad. El dato comparado en JS sigue en minúsculas.

## 3. Typography

Sin CDN de fuentes. `body` usa `--mt-font-sans`. Evidencia, ids, URLs, `field_source` y timestamps usan `--mt-font-mono`.

| Rol | Clase | Tamaño / peso / color | Uso |
| :--- | :--- | :--- | :--- |
| Page title | `.mt-title` | 20px / 600 / `--mt-fg` | Un `h1` por página |
| Section title | `.mt-section` | 13px / 600 / `--mt-muted`, tracking 0.04em, uppercase | `h2` de bloque |
| Body | `.mt-body` | 14px / 400 / `--mt-fg` | Párrafos |
| Label | `.mt-label` | 12px / 600 / `--mt-muted` | `<label>` |
| Metadata | `.mt-meta` | 12px / 400 / `--mt-muted` | Contadores, fechas |
| Technical | `.mt-tech` | 12px / 400 / `--mt-fg`, mono, `overflow-wrap: anywhere` | URLs, snippets en tabla |
| Code / evidence | `.mt-evidence` | 12px / 400 / `--mt-fg`, mono, pre-wrap, break-all | `<pre>` del snippet |
| Status | badge de la sección 2 | 11px / 600 | Junto al texto, nunca solo un punto de color |

No subir el `h1` a 30px+. La herramienta se lee en tablas.

## 4. Spacing

Escala de 4px (`--mt-space-1` … `--mt-space-7`).

- Página: padding `--mt-space-5` horizontal, `--mt-space-5` arriba.
- Entre secciones: `--mt-space-5`.
- Dentro de un panel: `--mt-space-4`.
- Entre label e input: `--mt-space-1`.
- Celdas de tabla: 8px 12px. Cabecera 8px 12px.
- Grupos de botones: gap `--mt-space-2`.

No mezclar `p-8` en un panel y `p-3` en el hermano para el mismo rol.

## 5. Borders

- Panel y tabla: 1px solid `--mt-border`.
- Input en reposo: 1px solid `--mt-border-strong`.
- Input en foco: 1px solid `--mt-accent` más `outline: 2px solid var(--mt-focus); outline-offset: 2px`.
- Separadores de fila: 1px solid `--mt-border` al 100%, no un gris más claro inventado por fila.
- El drawer se separa con borde izquierdo `--mt-border-strong`, no con cristal.

## 6. Radius

- Inputs, botones, paneles, alerts: `--mt-radius-md` (4px).
- Badges: `--mt-radius-sm` (2px). No `rounded-full`.
- Tablas: radio solo en el contenedor, celdas a 0.
- Modal: `--mt-radius-md`. No `rounded-xl`.

Si todo queda a 4px, el radio deja de parecer “tarjeta de producto”.

## 7. Shadows

- Paneles de página: ninguna.
- Modal y drawer: `--mt-shadow-overlay` además del borde. No es el estilo de las secciones.
- Nada de sombra en badges, filas o KPIs.

## 8. Buttons

Clases. El estado disabled baja opacidad a 0.45 y `cursor: not-allowed`. Hover solo si no está disabled.

| Clase | Uso | Fondo / texto / borde |
| :--- | :--- | :--- |
| `.mt-btn-primary` | Una acción principal por vista: Start scan, Confirm and start scan, Create, Sign in | `--mt-accent` / `--mt-accent-fg` / mismo |
| `.mt-btn-secondary` | Cancel, Retry, descargas, Newer/Older | transparente / `--mt-fg` / `--mt-border-strong` |
| `.mt-btn-danger` | Delete, Remove feedback, revocar invitación | transparente / `--mt-danger` / `--mt-danger-border` |
| `.mt-btn-ghost` | Enlaces de nav que son botones, Dismiss | transparente / `--mt-muted` / none |

Tamaño único: padding 8px 12px, 14px, peso 600. No botones a ancho completo salvo el CTA del wizard y de auth (ahí `.mt-btn-primary` + utilidad `w-full`).

Filtros (`aria-pressed`): no son pills. Son `.mt-btn-secondary`. `aria-pressed="true"` usa borde `--mt-accent` y texto `--mt-accent-hover`. El valor interno del filtro sigue en minúsculas; el texto visible puede ser Title Case.

## 9. Inputs

`.mt-input` para `input`, `textarea`, `select`:

- fondo `--mt-bg`
- texto `--mt-fg`
- borde de la sección 5
- radio 4px
- padding 8px 12px
- fuente 14px; los campos técnicos (dominios, ids) añaden `.mt-tech` sin cambiar el control
- placeholder: `--mt-faint`
- `min-height` del textarea según filas ya usadas (targets 4, dominios 3, descripción 2)

Label siempre visible, asociado por `for`/`id`. No sustituir labels por placeholders.

Checkbox del modal: control nativo, sin redibujarlo con un `div`. El anillo de foco usa `--mt-focus`.

Archivo de import en scopes: quitar el `style="color:#ffffff;..."` inline. Usar `.mt-input` y texto `--mt-fg` para que el nombre de fichero se lea en oscuro.

## 10. Cards

No hay un componente “card” genérico. Hay **paneles**:

`.mt-panel` — fondo `--mt-surface`, borde `--mt-border`, radio 4px, padding 16px.

Usos: formulario, grupo de KPIs (el grupo es un panel; cada cifra no es una tarjeta con sombra), bloque de import, banner de código de invitación.

KPI: `.mt-kpi` dentro del panel. Label `.mt-section`, cifra 22px/600 `--mt-fg`, línea secundaria `.mt-meta`. La cifra de findings no va en verde.

## 11. Tables

Contenedor `.mt-table-wrap` (`overflow-x: auto`, borde, radio 4px, fondo `--mt-surface`).

Tabla: ancho mínimo 100%, `border-collapse: collapse`, 14px.

- `caption` solo para lectores (clase `sr-only` de Tailwind, ya usada).
- `th`: `.mt-section`, alineado a la izquierda, `scope="col"`.
- `td` numérico: tabular, alineado a la derecha en Assets, Findings, Mentions, Occurrences.
- Fila hover: fondo `--mt-elevated`. Fila con foco de teclado (findings): `outline: 2px solid var(--mt-focus)`.
- Evidencia truncada con `MetaTracerUI.truncate` como ahora (90 / 60). El snippet completo solo en el drawer.

## 12. Tabs

Users conserva `role="tablist"` / `role="tab"` / `aria-selected`.

- Inactivo: `.mt-btn-secondary`
- Activo: fondo `--mt-elevated` + borde `--mt-accent` + texto `--mt-fg`

Una sola convención en las dos pestañas. El panel visible sigue siendo `<section>` con `aria-label` actual.

No usar tabs para severity/type del run: esos son filtros con `aria-pressed`.

## 13. Badges

`.mt-badge` + modificador:

- `.mt-badge-critical|high|medium|low|info|unclassified`
- `.mt-badge-pending|running|completed|failed|aborted`
- `.mt-badge-confidence` (neutro)

Siempre con nodo de texto. Un punto de color opcional va `aria-hidden="true"` y no sustituye la palabra.

Mapeo de presentación (el `x-text` deja de imprimir el enum crudo en badges):

```text
critical → Critical
high → High
medium → Medium
low → Low
info → Info
unclassified → Unclassified
pending → Pending
running → Running
completed → Completed
failed → Failed
aborted → Aborted
```

Los comparadores Alpine (`severityFilter === sev`, `statusFilter === status`) siguen usando la clave en minúsculas.

`finding_type` en dashboard: seguir el mapa ya existente (`gps` → GPS, `email` → Email, `internal_path` → Internal path, `software_version` → Software version, `debug_comment` → Debug comment). En el run, preferir `type_label` del API.

## 14. Alerts

| Clase | Cuándo | Rol ARIA |
| :--- | :--- | :--- |
| `.mt-alert-danger` | error de carga, scan failed, findings unavailable, form error | `role="alert"` si el contenido aparece sin mover el foco |
| `.mt-alert-warning` | status `aborted`; aviso 403 operator | `role="alert"` |
| `.mt-alert-neutral` | cero findings; empty de dashboard | sin role de error |
| `.mt-status` | import correcto, “Saving…” | `role="status"` o `aria-live="polite"` |

Fondo y borde de los tokens danger/warning/success. Texto 14px `--mt-fg`. El `error_message` del run en mono, `whitespace-pre-wrap`, `x-text`.

Asset issues: `.mt-alert-warning` o un `<details>` con borde warning, **no** `.mt-alert-danger`. El run no ha abortado.

Retry conserva la clase de botón secondary y la palabra `Retry`.

## 15. Loading

`.mt-loading`: fila con texto “Loading dashboard…”, “Loading run…”, “Loading history…”, “Loading scopes…”, “Loading users…”, “Loading invitations…”, “Loading more…”.

Spinner: borde `--mt-border-strong`, tope `--mt-accent`, 16px. Una vuelta, no un glow. Con `prefers-reduced-motion: reduce`, `.mt-spin { animation: none }`.

No skeletons de tarjeta. El formulario de `/` no tiene loading inicial (TASK-20: n/a).

## 16. Empty states

`.mt-empty` dentro de `.mt-panel`, alineado a la izquierda en tablas anchas y centrado solo en dashboard/history cuando es el único contenido. Título `.mt-title` a 16px. Cuerpo `.mt-body` en `--mt-muted`. Una acción como mucho (enlace a `/` con texto `New scan`).

Textos que se conservan:

- Dashboard: `No data yet`
- History: `No runs yet`
- Scopes: `No scopes yet`
- Run: `No findings`
- Users: `No users yet.` / `No invitations yet.`
- Campana: `No notifications yet.`
- Top domains vacío: `No scopes or assets scanned yet.`
- Top evidence vacío: `No findings yet.`

Cero findings no usa fondo success. Es un resultado válido, neutro.

## 17. Error states

Patrón único: `.mt-alert-danger` + mensaje de `readError` + `Retry` donde la página ya lo tiene.

Mensajes de `/` que no se reescriben:

- `Another scan is already running; wait for it to finish.`
- `The scope confirmation was rejected by the server.`
- `Enter at least one target.`
- `Enter at least one authorized scope domain or choose a saved scope; the scope is never inferred from the target.`

Run desconocido: título `Run not found` y el párrafo actual sobre la base local.

No mostrar stack traces. `error_message` ya viene saneado del servidor; igual se escapa con `x-text`.

## 18. Severity visualization

En dashboard, por cada clave de `severityOrder` (`critical`, `high`, `medium`, `low`, `info`) más una línea `unclassified`:

- Etiqueta Title Case
- Entero (`severityCount`)
- Barra de 8px de alto, radio 2px, color de **esa** severidad (`background: var(--mt-sev-…)`), ancho `severityWidth(sev)%` vía `:style` con número. Track de 100% en `--mt-border`.
- Si la cuenta es 0, la barra tiene ancho 0 y el “0” sigue visible.

Eliminar la clase `.severity-bar` con gradiente único cuando el dashboard deje de usarla. No hay heatmap.

En la tabla de findings el badge es el de la sección 13. Orden de filas: el que devuelve el API. El cliente solo filtra.

## 19. Animation principles

Permitido:

- Cambio de color en 120ms en hover/focus de botones y filas.
- Aparición del modal/drawer: opacidad 120ms. Sin slide largo.
- Spinner de la sección 15 mientras `running`, `starting` o loading.
- `x-cloak` se mantiene (ya está en `metatracer.css`).

Prohibido: animación de fondo, pulso infinito en badges, contadores que “cuentan” hasta el número, transiciones de layout al filtrar.

`@media (prefers-reduced-motion: reduce)` anula transiciones y el spinner.

## 20. Patrones Tailwind que sí se usan

Layout, no tema:

- Página autenticada: el main no lleva `max-w-6xl` heredado si el sidebar ya limita; el bloque de contenido usa `min-w-0` para que las tablas puedan encoger.
- Wizard: `max-w-2xl` puede quedarse.
- Auth: `max-w-md mx-auto`.
- Grids de KPI: `grid grid-cols-2 lg:grid-cols-4 gap-4`.
- `x-cloak`, `sr-only`, `min-w-0`, `break-all` donde haga falta además de `.mt-tech`.

Sustituir en el rediseño, cuando se toque la plantilla: `bg-slate-*`, `text-emerald-*`, `border-slate-*`, `bg-emerald-600`, `rounded-lg`, `rounded-full` de badges. No hace falta un barrido mecánico el día 1: cada fase migra las plantillas que posee.

## 21. Drawer de finding (composicion visual)

Tres zonas, en este orden, dentro del mismo `<aside>`:

1. **Identity** — `title`, badge de severity, `type_label`, `Confidence` + valor.
2. **Evidence** — encabezado `Evidence`. `evidence_snippet` en `.mt-evidence`. `field_source`, `asset_source_url`, `asset_final_url` (ancla solo vía `safeUrl`), `asset_content_type`. Botón `Copy` / `Copied`.
3. **AI analysis** — contenedor `.mt-panel` con borde `--mt-border-strong` y un rótulo permanente: `AI analysis — not evidence`. Dentro, y solo ahí: `Justification` (`severity_justification`), `Impact` (`impact_analysis`), `Reproduction steps` (`reproduction_steps`), `Remediation` (`remediation_advice`). Si un string viene vacío, se omite ese subtítulo; no se rellena con texto inventado.
4. **Feedback** — separado por borde superior, título `Feedback`, controles actuales. No entra en Evidence ni en AI analysis.

Copy del rótulo de IA, normativo: `AI analysis — not evidence`.

## 22. Scrollbars

El bloque actual de `metatracer.css` se recolorea con `--mt-border` y `--mt-bg`. Se conserva `x-cloak`.
