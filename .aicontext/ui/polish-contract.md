# Contrato visual de pulido — Web V2

**Estado:** vigente como **extensión** de [`design-system-v2.md`](design-system-v2.md). No lo sustituye.  
**Spec:** [`specs/52-ui-polish.md`](../../specs/52-ui-polish.md) (`closed`).  
**Agente:** `v2-ui-engineer` implementa; `ui-architect` no toca `web/`.  
**Mandato:** más clara y más rápida de operar. No look de landing. No animaciones de adorno.

Si este contrato y el CSS discrepan en **color**, manda `web/src/app/globals.css`.  
Si discrepan en **jerarquía o cromo de estas superficies**, manda este documento.

Specs 36–53 closed. Overlay v3.4 sin reserved. No inventa producto.

---

## 1. Intención y principios

**Qué mejora.** Jerarquía de página (un `h1`, un kicker con significado, una CTA primaria), cromo que frena el trabajo diario (pestañas de dos líneas, cabezas duplicadas del run, “siguientes pasos” de tres tarjetas, wizard con pipeline decorativo, login con rejilla y dibujo animado) y estados vacíos/carga que ocupan una tarjeta de dashboard fuera del Panel.

**Qué no se toca.** Paleta `--mt-*`, densidad `html[data-density]`, procedencia (`LayerChip`: Observado / Inferido / Externo ≠ severidad), rúbrica, gate de alcance, un origen, cero CDN, texto no HTML del target, `safeUrl()`, CSRF, SSE, enums. Ni ZIP, Wayback seed, HEIC, grafo, tiles ni pantallas nuevas.

**Principios (además del design system §1):**

1. **Una pregunta por pantalla.** El operador sabe en 1 s qué hacer ahora.
2. **Cromo bajo.** Quitar rieles, iconos de adorno, hints en pestañas, fondos de cuadrícula y diagramas que se dibujan.
3. **Kicker ≠ título.** `.mt-kicker` etiqueta un bloque. Nunca un número suelto, nunca un `h2`.
4. **Una CTA `primary` por vista.** El resto es `secondary` / `ghost` / `danger`.
5. **Movimiento solo al cambiar de estado.** Design system §6.

Copy de UI: **español** (spec 45). Enums en datos: minúsculas inglesas.

---

## 2. Superficies

### En alcance

| Ruta | Componentes / clases |
| :--- | :--- |
| `/dashboard` | `dashboard-view.tsx`, `metric-card.tsx`, onboarding, “Qué hacer ahora” |
| `/` | `scan-wizard.tsx`, `.mt-wizard-grid`, `.mt-wizard-span`, modal de alcance |
| `/runs/[runId]` | `run-progress.tsx`, `live-activity.tsx`, `.mt-live`, `.mt-live-sweep` |
| `/runs/[runId]/{assets,metadata,findings,coverage}` | `run-workspace-shell.tsx`, `run-header.tsx`, `.mt-tabs` / `.mt-tab` |
| Hallazgos | `findings-panel.tsx`, `filters-bar.tsx`, `finding-detail.tsx`, `SplitPane` / `.mt-workspace` |
| `/search` | `search-view.tsx` |
| `/investigations`, `/investigations/[id]` | `investigations-view.tsx`, `investigation-detail.tsx` |
| `/runs/compare` | `compare-view.tsx` |
| `/login` (y register/setup si comparten cromo) | `auth-panel.tsx`, `auth-stage.tsx`, `capture-diagram.tsx`, `.mt-auth*` |
| Primitivos | `states.tsx` (`EmptyState`, `LoadingState`), `.mt-page-head`, `.mt-page-title` |

Historial (`history-view.tsx`): pulido ligero de cabeza. Una CTA primaria “Nuevo escaneo”; “Comparar selección” es `secondary` y solo con 2 ids.

### Fuera de alcance

Usuarios, webhooks, integraciones, conocimiento, alcances: no rediseñar; si se toca `EmptyState`/`LoadingState`, heredan el primitivo. GPS map, rollups de cobertura, chips de procedencia: ya correctos. Paleta y `theme.test.tsx` salvo lo que exija quitar motion de auth. Producto nuevo, V1, CORS, CDN, markdown-a-HTML.

---

## 3. Tokens

**Solo `--mt-*` existentes.** Cero tokens de color nuevos.

Clases nuevas permitidas (sin variables de color):

- `.mt-tab` más compacto: una línea; el hint va a `title` / `aria-label`, no a un segundo `<span>`.
- `LoadingState` con `variant="page" | "list"` (layout, no color).
- `.mt-empty` opcional: mismo `.mt-card` con `padding: var(--mt-space-4)`.

No hace falta `--mt-empty-*` ni `--mt-tab-*`.

---

## 4. Por superficie: actual → deseado

Regla global: **toda página de trabajo usa `.mt-page-head` + un `h1.mt-page-title`**. Lede en `.mt-meta` o `text-sm text-mt-muted`. Acciones a la derecha. Un `h1`.

### 4.1 Panel — `dashboard-view.tsx`

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Onboarding de 3 `.mt-card` con kicker `1/2/3`. Con datos: fila “Qué hacer ahora” de 3 tarjetas + 4 métricas + gráficos + uso de IA duplicado al pie. | Vacío: **un** `EmptyState` + CTA `Iniciar el primer escaneo`. Con datos: quitar la fila de 3 tarjetas. Una línea de siguiente paso (texto + enlace). Métricas + gráficos existentes. Quitar el bloque inferior de tokens si ya está en “Uso de IA”. |
| Tipografía | `h1.mt-page-title` OK. Kickers numéricos. `MetricCard` usa `h2.mt-kicker`. | Kicker solo para etiquetas de métrica (`p.mt-kicker`, no heading). El valor es `.mt-metric-value`. |
| Densidad | Iconos 32px + riel. Hallazgos usa `bg-mt-sev-high` siempre. | Quitar el recuadro de icono. Riel izquierdo: `--mt-border-strong` o `--mt-accent`, **nunca** color de severidad. |
| CTA | `Nuevo escaneo` es `secondary` en la cabeza. | **Una** `primary`: `Nuevo escaneo`. |

### 4.2 Wizard — `scan-wizard.tsx`

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | `.mt-wizard-grid`. Paso 3 a ancho con profundidad + submit. Debajo, “Recorrido” con `.mt-stages` todos `pending`. | Conservar grid. HTTP vs local: radios → `Button variant="toggle"` con `aria-pressed`. Un solo bloque de campos visible. Paso 3: profundidad a la izquierda, **CTA a la derecha en la misma fila**. Quitar “Recorrido”: el pipeline vive en la página del run. |
| Tipografía | Kickers “Paso 1/2/3” correctos. `h1.mt-title`. Lede largo. | `h1.mt-page-title`. Lede de una frase. Kickers se quedan. |
| HTTP vs local | Mismo peso; el texto de rutas es el único distintivo. | Origen activo pulsado (borde acento). Ayuda local se mantiene (cero bytes; no `<input type="file">`). |
| CTA | `Iniciar escaneo` en el paso 3; el modal confirma. | Submit: **única** `primary` de la página. Modal: Cancelar `secondary` (foco inicial), Confirmar `primary` disabled hasta el checkbox. Viewer: sin primary. |

### 4.3 Run: resumen vs workspace

**Deuda:** `/runs/[id]` (`run-progress.tsx`) pinta una cabeza a mano **y** mete `FindingsPanel` entero. Las pestañas Activos/Metadatos/Hallazgos/Cobertura usan `RunWorkspaceShell` + `RunHeader`. Dos cromos para el mismo run.

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Resumen = header distinto + tabs + ExportLinks + ghost Comparar/Historial + LiveActivity o CorrelationPanel + **tabla completa de hallazgos**. Tabs con label + hint, `flex: 1 1 8rem`. | **Un solo cromo:** resumen también bajo `RunWorkspaceShell` / el mismo `RunHeader`. Resumen: estado, LiveActivity si `running`/`pending`, alertas failed/aborted, CorrelationPanel si completed, AssetIssues, CTA a Hallazgos. **No** duplicar `FindingsPanel` en resumen. Export: una fila compacta, no una `.mt-card` de ensayo. |
| Tabs | Dos líneas; se envuelven y parecen tarjetas. | `.mt-tab`: solo el label. Hint en `title` y `aria-label` de la nav. `flex: 0 1 auto`; subrayado acento. Activo: borde inferior `--mt-accent` + texto `--mt-fg`. |
| Tipografía | `h1.mt-title` + `run_id` en `.mt-tech`. | Igual, dentro de `.mt-page-head`. Un `h1`. |
| CTA | En vivo: Abortar (`danger`). Terminado: Eliminar es el botón más visible. | En vivo: Abortar es la única acción fuerte. Terminado: Eliminar sigue `danger` pero no es la acción por defecto. Un `primary` máximo: si completed y hay hallazgos, “Ver hallazgos” `primary`; si no, “Nuevo escaneo” `secondary`. |

### 4.4 Hallazgos / split

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Filtros (varias filas) + mapa + AssetFindings + barra masiva + tabla en split. `FindingDetail` con `gap-6`. | Filtros: primera fila = severidad + búsqueda `/`. Segunda = tipo / confianza / triaje. Mapa y agrupación de asset **después** de la tabla o colapsados si no hay GPS. Split: lista izquierda, detalle derecha ≥1024px; `<1024` Sheet. Handle 6px, `[`/`]` sin cambio. |
| Tipografía | Evidencia `.mt-evidence` + `LayerChip` Observado; IA con Inferido. Correcto. | Conservar orden evidencia → campo → URLs → análisis. `gap` = `--mt-space-4`. |
| CTA | Copiar `secondary`. Triaje en el panel. | Sin primary en el detalle. La fila seleccionada (`aria-selected` + inset acento) es el foco. |

### 4.5 Buscar — `search-view.tsx`

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Sin `.mt-page-head`. `gap-6`. Selects con `border-mt-border`. Hits con enlace `text-mt-accent`. | `.mt-page-head`. Formulario tipo `.mt-command`: query flex + **Buscar** `primary`. Filtros en una fila, `border-mt-border-strong`, `bg-mt-bg`. Resultados: `.mt-card` + lista densa o `.mt-table`; título/tipo en `--mt-fg`; evidencia `.mt-tech` / `.mt-evidence`; enlace con underline, no cian de marketing. |
| Vacío | `EmptyState` grande. `LoadingState` de 4 cards. | Vacío compacto. Loading `variant="list"`. |
| CTA | `Buscar` ya es primary. | Se mantiene; es la única. |

### 4.6 Investigaciones

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Lista: `h1` suelto + form `.mt-card` + tabla cruda. Detalle: breadcrumb + flex sin `.mt-page-head`. Badge Cerrada = `aborted`. | Lista: `.mt-page-head` + form en la cabeza si operator (input + **Crear** `primary`). Tabla `.mt-table` / `.mt-row`. Detalle: `.mt-page-head`, `h1` = nombre. Badge: Abierta tono `running` o `pending`; Cerrada tono `completed` o `pending` — **nunca** `aborted`. |
| Vacío | Copy OK. | `EmptyState` compacto. Loading `list`. |
| CTA | Crear. Cerrar investigación. | Lista: Crear. Detalle: Cerrar = `secondary` o `danger`; no sumar botones. |

### 4.7 Comparar — `compare-view.tsx`

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | `h1` suelto. `EmptyState` a pantalla cuando faltan ids. Tres `.mt-card` de secciones. | `.mt-page-head`. Selects en `.mt-command`. Placeholder “elige dos” = `.mt-meta`, no empty card a toda altura. Secciones con dato real siguen en `.mt-card`. |
| CTA | No hay primary (la acción es elegir). | Correcto: ningún `primary` hasta haber par; entonces el GET pinta, sin botón extra. |

### 4.8 Login — `.mt-auth`, `capture-diagram.tsx`

| | Actual | Deseado |
| :--- | :--- | :--- |
| Layout | Viewport lleno, **rejilla de fondo**, diagrama SVG (≥960px) con spokes que se dibujan, nodos, `animateMotion` (`.mt-auth-signal`). Panel 28rem. | Fondo `--mt-bg` **liso**. Diagrama **estático** o ausente &lt;960px; si se conserva ≥960px, sin animación. Panel: kicker “Sesión”, un `h1`, lede corto, form, una `primary` a ancho. |
| CTA | `Iniciar sesión` `w-full` primary. | Se mantiene. |

### 4.9 Primitivos

**`EmptyState`:** padding `--mt-space-4`. Título `.mt-section-title`. Cuerpo `text-sm text-mt-muted`. Acción opcional como children.

**`LoadingState`:** `variant="page"` = 4 skeletons (solo Panel). `variant="list"` = 2–3 barras `.mt-skeleton` (resto). `role="status"` `aria-busy`. Skeleton **estático**.

**Shell:** no rediseñar sidebar/topbar ni `.mt-brand-mark`.

---

## 5. Movimiento

**Permitido:**

- Color / borde / fondo en hover y focus: `160ms` `--mt-duration` `--mt-ease`.
- `width` de `.mt-live-sweep > span` cuando el servidor informa un paso.
- `.mt-spin` solo mientras hay carga acotada.
- Reloj `formatElapsed` (texto tabular, no count-up).

**Prohibido:**

- Loops salvo `mt-spin`.
- Shimmer, partículas, count-up, grafos, `mt-sweep` / `mt-pulse`.
- `@keyframes mt-auth-draw`, `mt-auth-arrive`, `.mt-auth-spoke*`, `.mt-auth-node` con delay, `<animateMotion>` / `.mt-auth-signal`.
- Transición de aparición de tarjetas del panel o del wizard.
- Animar `.mt-stage*` en el wizard (el wizard ya no muestra el recorrido).

`prefers-reduced-motion: reduce` sigue anulando transiciones y `mt-spin`. Tras quitar keyframes de auth, `theme.test.tsx` debe seguir: ningún `animation: … infinite` excepto `mt-spin`.

---

## 6. A11y

- Un `h1` por ruta. Kickers no son headings. Métricas: `p.mt-kicker` + valor; el `h2` de sección es “Severidad”, “Tipos”, etc.
- Foco `:focus-visible` `--mt-focus` 2px offset 2px.
- Contraste AA ambos temas: no tocar pares de color. Tabs: `aria-current="page"` + subrayado, no solo color.
- Atajos actuales (`/`, `j`/`k`, `x`, `[`/`]`, `Ctrl+K`, `?`) muertos en `isTypingTarget`. No añadir atajos.
- Wizard: `fieldset`/`legend` para origen. Modal: foco inicial Cancelar; checkbox desmarcado.
- Login: diagrama `role="img"` con `aria-label`; el form no depende de él.
- Target: nodos de texto; evidencia en `<pre class="mt-evidence">`.

---

## 7. Copy (español UI)

| Sitio | Usar |
| :--- | :--- |
| Panel vacío | Título: `Aún no hay escaneos`. Cuerpo: `Confirma el alcance e inicia el primero.` CTA: `Iniciar el primer escaneo`. |
| Panel con datos | Quitar “Qué hacer ahora” de tres tarjetas. Si hay sin clasificar: `N hallazgos sin severidad` + enlace. |
| Wizard lede | `Documentos públicos dentro del alcance que confirmes. El alcance no se copia de los objetivos.` |
| Origen | `Crawl HTTP` / `Carpeta local`. |
| Run tabs | Resumen, Activos, Metadatos, Hallazgos, Cobertura (hints fuera del cromo). |
| Resumen sin tabla | `Los hallazgos están en la pestaña Hallazgos.` + enlace. |
| Buscar vacío | `Escribe una consulta` / `No inicia un escaneo.` |
| Comparar | `Elige una línea base y un escaneo a revisar.` (meta, no empty card). |
| Investigación cerrada | Badge `Cerrada` (no reutilizar Abortado). |
| Login lede | `Descubrimiento autorizado de metadatos. Cada escaneo sigue pidiendo alcance confirmado.` |
| LayerChip | Conservar `Observado` / `Inferido` / `Externo`. |

Reportes exportados y CLI: inglés. `detail` de API: no traducir.

---

## 8. Qué no hacer

- Look de landing, hero, rejilla, diagrama animado, “Intelligence platform”, glass, gradientes, `rounded-full` en badges.
- Más animación, shimmer, count-up, confetti, skeleton animado.
- Nueva paleta, tokens de color, CDN de fuentes, Lucide extra decorativo.
- Inventar unpack ZIP, seed Wayback, HEIC, grafo OSINT, Settings, chat.
- `dangerouslySetInnerHTML`, markdown-a-HTML, `javascript:` / `data:`.
- Segunda CTA primary, o Eliminar como botón por defecto del run completed.
- Usar `.mt-kicker` como `h2` o como `1`/`2`/`3`.
- Pintar severidad con el riel de una métrica o con el badge de investigación.
- Duplicar `FindingsPanel` en Resumen y en `/findings`.
- Reintroducir Web V1, CORS, segundo host, tiles.
- i18n bilingüe / `next-intl`.
- “Recorrido” decorativo en el wizard.
- `<input type="file">` o upload de bytes.
- Ampliar `LoadingState` de 4 métricas a todas las páginas.

---

## 9. Criterio de hecho (`v2-ui-engineer`)

- [ ] Ningún archivo fuera de `web/` (y tests de `web/`). No tocar `src/metatracer/` ni `.cursor/agents/`.
- [ ] `design-system-v2.md` no contradicho; 0 tokens de color nuevos.
- [ ] Cada ruta en alcance: un `h1.mt-page-title`, cabeza `.mt-page-head` salvo login, **≤1** `Button variant="primary"`.
- [ ] Kickers solo como etiqueta de bloque; `MetricCard` sin `h2.mt-kicker` y sin riel de severidad.
- [ ] Wizard: HTTP/local con toggle visible; sin `.mt-stages` en `/`; CTA en paso 3; modal intacto (checkbox, foco Cancelar, `scope_confirmed` solo al confirmar).
- [ ] Run: mismo header/tabs en resumen y workspace; tabs de una línea; hallazgos completos solo en `/findings`.
- [ ] Split ≥1024px / Sheet &lt;1024px; `[`/`]` y densidad sin cambio de contrato.
- [ ] `EmptyState` compacto; `LoadingState` `list` fuera del Panel.
- [ ] Login: sin grid CSS; sin keyframes/auth motion; una primary.
- [ ] Copy UI en español; LayerChip en español; enums de datos intactos.
- [ ] `theme.test.tsx` verde: AA, light=system-light, ningún infinite salvo `mt-spin`.
- [ ] Vitest de las superficies tocadas verde; Playwright wizard+auth si el cromo de login cambia.
- [ ] `git diff` sin producto nuevo ni dependencias nuevas.
