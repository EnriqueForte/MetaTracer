# Design system — Web V2 (`web/`)

**Estado:** vigente desde la Fase 0 (2026-10-25). **Sustituye** a
[`design-system.md`](design-system.md), que describe la Web V1 (Jinja + Alpine) y se
conserva solo como histórico.

**Implementación normativa:** `web/src/app/globals.css` (tokens `--mt-*` y clases de
componente) más utilidades Tailwind 4 en los componentes de `web/src/components/ui/`.
**Verificación automática:** `web/src/components/shell/theme.test.tsx` comprueba que el
tema claro y el oscuro cumplen WCAG AA y que no existe ninguna animación permanente.

Si este documento y el CSS discrepan, **manda el CSS**; abre un cambio para
corregir el documento en el mismo PR.

---

## 1. Principios

1. **Precisión sobre decoración.** Cada bloque responde a un dato o a una acción que ya existe.
2. **Evidencia sobre ruido.** Lo que el extractor observó se lee antes que lo que el modelo interpreta.
3. **Un significado por color.** La severidad tiene su escala; el acento es acción y foco; la
   procedencia (`observed` / `inferred` / `external`) es otra escala distinta y **nunca** se usa
   para indicar gravedad.
4. **Densidad alta, cromo bajo.** Bordes de 1px, sombras casi inexistentes, radios pequeños.
5. **El color no es el único canal.** Severidad, estado, triaje y procedencia llevan siempre texto.
6. **Movimiento solo al cambiar de estado.** Prohibida cualquier animación en bucle.
7. **Monoespacio donde ayuda a leer.** Evidencia, hashes, campos, URLs, IDs, tamaños. Nunca en prosa.

Prohibido: estética de terminal con verde neón dominante, glassmorphism, gradientes decorativos,
partículas, gráficos sin dato, contadores que "cuentan" hasta el número, grafos sin una pregunta
del analista detrás.

---

## 2. Tokens

Los valores viven en `globals.css`. Tres bloques de tema deben permanecer sincronizados:
`:root` (oscuro), `:root[data-theme="light"]` y `:root[data-theme="system"]` (bajo
`prefers-color-scheme: light`). Un test verifica que los dos últimos son idénticos.

### Superficies, líneas y texto

Valores vigentes (CSS). Oscuro es el default; claro se declara dos veces (light y system-light).

| Token | Oscuro | Claro | Uso |
| :--- | :--- | :--- | :--- |
| `--mt-bg` | `#06080c` | `#f4f6f9` | Fondo de la aplicación |
| `--mt-surface` | `#0c1118` | `#ffffff` | Paneles, tablas, tarjetas, sidebar, topbar |
| `--mt-elevated` | `#131a24` | `#e8eef4` | Hover de fila, panel elevado, fondo de dialog |
| `--mt-overlay` | `rgba(6, 8, 12, 0.82)` | `rgba(13, 21, 32, 0.48)` | Velo de modal y drawer |
| `--mt-border` | `#1c2430` | `#d4dde8` | Separadores de 1px |
| `--mt-border-strong` | `#5c6e84` | `#6f8196` | Bordes de input y de chip (≥ 3:1) |
| `--mt-fg` | `#eaeff6` | `#0d1520` | Texto principal |
| `--mt-muted` | `#9aa9bb` | `#445566` | Texto secundario y labels |
| `--mt-faint` | `#8b9aab` | `#536274` | Metadata de baja jerarquía |

### Acento y foco

Oscuro: `--mt-accent` `#3cc4dc`, `--mt-accent-hover` `#6ad6ea`, `--mt-accent-fg` `#041218`, `--mt-focus` `#8ee4f2`.
Claro: `--mt-accent` `#0c6f86`, `--mt-accent-hover` `#0a5870`, `--mt-accent-fg` `#ffffff`, `--mt-focus` `#0a5870`.
El acento es **acción y foco**, nunca severidad ni éxito. Cian de instrumento, no verde neón.

### Severidad (presentación)

| Dato | Etiqueta | Fondo | Texto |
| :--- | :--- | :--- | :--- |
| `critical` | Critical | `--mt-sev-critical-bg` | `--mt-sev-critical` |
| `high` | High | `--mt-sev-high-bg` | `--mt-sev-high` |
| `medium` | Medium | `--mt-sev-medium-bg` | `--mt-sev-medium` |
| `low` | Low | `--mt-sev-low-bg` | `--mt-sev-low` |
| `info` | Info | `--mt-sev-info-bg` | `--mt-sev-info` |
| `null` | Unclassified | `--mt-sev-unclassified-bg` | `--mt-sev-unclassified` |

El dato viaja en minúsculas; el badge muestra Title Case. `unclassified` no es un valor del
enum: es la presentación de `severity = null`.

### Estado de ejecución (no es severidad)

`pending` / `running` / `completed` / `failed` / `aborted`, cada uno con su token. `completed`
no usa el color del botón primario.

### Procedencia (U0, nuevo)

| Token | Significa | Uso |
| :--- | :--- | :--- |
| `--mt-layer-observed` | Dato leído del archivo | Campo extraído, evidencia |
| `--mt-layer-inferred` | Derivado o interpretado | Severidad heurística, análisis del modelo |
| `--mt-layer-external` | Vino de un proveedor | Captura de Wayback, registro RDAP |

Se renderizan como texto (`Observed`, `Inferred`, `External`), no solo como color.

### Densidad (U0, nuevo)

| Token | Valor |
| :--- | :--- |
| `--mt-row-h-comfortable` | `44px` |
| `--mt-row-h-compact` | `32px` |
| `--mt-row-h` | El elegido |
| `--mt-font-evidence` | `12px` (`11px` en compacto) |
| `--mt-font-table` | `13px` (`12px` en compacto) |

La densidad se aplica con `html[data-density="compact"]`, de modo que cambiar de modo **no**
re-renderiza React y las tablas siguen el cambio solas.

### Workspace (U0, nuevo)

`--mt-panel-min` (320px), `--mt-panel-default` (420px), `--mt-panel-max` (720px),
`--mt-split-handle`, `--mt-split-handle-active`.

---

## 3. Tipografía

Sin CDN de fuentes. Solo caras del SO:

- `--mt-font-sans`: Segoe UI Variable / Inter / IBM Plex Sans / system-ui
- `--mt-font-mono`: Cascadia Code / IBM Plex Mono / JetBrains Mono / ui-monospace

El `body` usa `font-optical-sizing: auto`, antialiasing y `letter-spacing: -0.011em`.
`.mt-tech` y `.mt-evidence` desactivan ligaduras (`liga`/`calt`) para hashes y evidencia.

| Rol | Clase | Uso |
| :--- | :--- | :--- |
| Page title | `.mt-page-title` / `.mt-title` | Un `h1` por página |
| Page head | `.mt-page-head` | Título + acciones, con regla inferior |
| Section title | `.mt-section-title` | `h2` de bloque |
| Kicker | `.mt-kicker` | Etiqueta superior de un panel |
| Metadata | `.mt-meta` | Contadores, fechas |
| Technical | `.mt-tech` | URLs, campos, IDs |
| Evidence | `.mt-evidence` | `<pre>` del snippet, `pre-wrap`, `break-all` |

El tamaño de `.mt-evidence` y de la tabla depende de la densidad (§2).

---

## 4. Espaciado, bordes y radios

Escala de 4px (`--mt-space-1` … `--mt-space-7`). Página: `--mt-space-5`. Entre secciones:
`--mt-space-5`. Dentro de un panel: `--mt-space-4`.

Bordes de 1px en paneles y tablas; input en reposo con `--mt-border-strong`; foco de input con
borde `--mt-accent` **más** `outline: 2px solid var(--mt-focus)` con `outline-offset: 2px`.

Radios: `--mt-radius-sm` (3px, badges y chips), `--mt-radius-md` (6px, inputs, botones),
`--mt-radius-lg` (8px, tarjetas). Nunca `rounded-full` en badges.

Cromo: sidebar y topbar sticky usan `--mt-surface` sobre `--mt-bg`. `.mt-card` lleva
`--mt-shadow-card` (inset 1px + sombra corta). `.mt-brand-mark` es un recuadro de 16px
con riel de acento a la izquierda. El wizard de escaneo usa `.mt-wizard-grid` (dos
columnas ≥ 960px). Las pestañas del run son `.mt-tabs` / `.mt-tab` (subrayado de acento,
no tarjetas). Checkboxes usan `accent-color: var(--mt-accent)`.

---

## 5. Componentes

### Botones (`web/src/components/ui/button.tsx`)

Variantes: `primary` (una sola acción principal por vista), `secondary`, `danger`, `ghost`,
`toggle` (filtros con `aria-pressed`, con estado pulsado visible por borde y color, no solo
anunciado). Disabled: opacidad 0.45 y `cursor: not-allowed`.

### Tablas (`web/src/components/ui/table.tsx`, `.mt-table`, `.mt-row`)

Cabecera con `th scope="col"`. Filas con `--mt-row-h`. Fila seleccionada: `aria-selected="true"`
más `box-shadow: inset 2px 0 0 var(--mt-accent)` — el color nunca es el único indicador. Fila con
foco de teclado: `outline: 2px solid var(--mt-focus)`.

Evidencia truncada en la tabla (90 / 60 caracteres); el valor completo solo en el panel de detalle.

### Badges (`web/src/components/ui/badge.tsx`)

Un badge por significado: severidad, estado, confianza, triaje. Siempre con nodo de texto.

### Estados (`web/src/components/ui/states.tsx`)

| Componente | Cuándo | ARIA |
| :--- | :--- | :--- |
| `LoadingState` | Carga inicial | `role="status"` `aria-busy="true"` |
| `EmptyState` | Resultado legítimamente vacío | Sin rol de error |
| `ErrorState` | Fallo de carga, con `Retry` | `role="alert"` |

El skeleton es **estático** (bloque `--mt-elevated`). No hay shimmer.

### Panel de detalle y split

`.mt-workspace` es un grid de dos columnas con `--mt-panel-width`. `.mt-split-handle` es un
control de 6px, `role="separator"`, navegable con teclado (`[` / `]`). Por debajo de 1024px el
llamador renderiza un `Sheet` en su lugar: el panel persistente es una mejora de escritorio, no
un requisito de lectura.

---

## 6. Movimiento

Permitido: transición de color en hover/focus (160ms) y transición de `width` en la barra de
progreso cuando el servidor reporta un paso nuevo.

Prohibido y verificado por test: `animation` con `infinite` salvo `mt-spin` (indicador de carga
acotado), y en general cualquier animación en bucle. Se retiraron `mt-sweep`, `mt-pulse`,
`mt-asset` y el shimmer de `mt-skeleton` en la Fase 0.

`@media (prefers-reduced-motion: reduce)` anula transiciones y el spinner.

---

## 7. Accesibilidad

- Contraste mínimo 4.5:1 para texto y 3:1 para bordes de control y foco, en **ambos** temas.
  `theme.test.tsx` lo comprueba token a token, incluidas las capas de procedencia.
- Foco siempre visible y nunca eliminado (`:focus-visible` con `--mt-focus`).
- Un solo `h1` por página; jerarquía de encabezados sin saltos.
- Los atajos de una tecla se desactivan mientras se escribe en un campo (`isTypingTarget`).
- Ningún dato del target se renderiza como HTML: todo es texto (`dangerouslySetInnerHTML` está
  prohibido) y las URLs pasan por `safeUrl()`, que solo acepta `http`/`https`.

---

## 8. Contrato de CSS con los tests

`theme.test.tsx` lee este CSS y verifica:

1. `:root[data-theme="light"]` y `:root[data-theme="system"]` definen exactamente los mismos tokens.
2. Los pares texto/fondo cumplen AA (incluidos `--mt-layer-*`).
3. No existe ninguna animación permanente excepto `mt-spin`, y no quedan los `@keyframes` retirados.
4. Existe `html[data-density="compact"]` con `--mt-row-h-compact`.

Cambiar un token obliga a pasar ese test; por eso el documento y el código no pueden divergir en
silencio.
