# Dirección visual de Web V2

Aceptada junto con [ADR-001](ADR-001-nextjs-react-migration.md) el 2026-09-26. Obliga a las fases de UI del [plan](../migrations/v1-to-v2-frontend.md). No obliga a Web V1: `.aicontext/ui/*` sigue siendo el contrato Jinja.

**Actualización 2026-09-29.** La paleta de acero y la severidad apagada dejan de aplicar a Web V2. Los tokens, la jerarquía y las fases siguientes están en [v2-analytics-ui.md](v2-analytics-ui.md). Siguen vigentes el resto de este documento: no inventar producto, no copiar la demo, datos del target como texto, y scope como gate.

Referencia observada: demo BugTrace (`https://demo.bugtraceai.com/bugtraceai`), revisión del 2026-09-26. Se toma la estructura de trabajo. No se toma el catálogo de producto ni la marca.

## Qué se adopta

La pantalla de trabajo es un lienzo, no un formulario largo.

1. **Barra de comando** arriba: targets, una sola fuente de scope, profundidad de razonamiento, acción primaria compacta. El modal de scope sigue siendo un gate: checkbox desmarcado, sin POST hasta confirmar.
2. **Canvas** debajo. Vacío: un estado gráfico breve (“Awaiting scan data”), no un párrafo suelto. Con `run_id`: las siete etapas del SSE, el asset en curso y el mensaje, como texto.
3. **Al terminar el run**, el mismo sitio muestra el resumen y la tabla. Barras Critical → Info y el total salen de los findings ya devueltos, o de `GET /api/stats` en el dashboard. No hay métricas nuevas.
4. **Fila expandible** con los campos que ya existen: evidencia en monoespacio; aparte, justificación, impacto, remediación y pasos de reproducción. Todo texto. `safeUrl` en los enlaces de asset.
5. **History** como tabla de runs. **Descargas** en los cinco formatos actuales (`md`, `json`, `html`, `csv`, `bounty`).
6. **Movimiento** solo al cambiar de estado: etapa SSE, apertura de fila, aparición del resumen. Sin partículas, sin neón, sin grafos decorativos.

La navegación sigue siendo la de MetaTracer: Dashboard, Reconnaissance, History, Scopes, Users. No se sustituye por la suite de diez herramientas de la demo.

Severidad: se conservan las etiquetas con texto y la escala ya definida (Critical apagado, High cobre, Medium ámbar, Low acero, Info gris, Unclassified sin relleno). El acento de acción sigue siendo el acero de `--mt-accent`, no el naranja de la demo. Un clon de su violeta haría que MetaTracer parezca otro producto.

## Qué no se adopta

| Elemento de la demo | Motivo |
| :--- | :--- |
| Chat, AIrepeater, Model Lab, Payload Tools, JWT Analyzer, PrivEsc, File Upload Auditor | No hay API ni flujo en MetaTracer |
| Grafo “swarm” / attack graph | No hay contrato de grafo. Split = etapas + findings. Events = el `ProgressEvent` que ya emite el bus |
| CVSS, petición/respuesta de exploit, “Proof of exploitation” | MetaTracer no calcula CVSS y el agente no genera payloads |
| Depth 5 y Max URLs 500 | Esos controles no existen. El crawl lo decide el backend |
| Selector de proveedor LLM | La configuración del modelo sigue en el servidor |
| ZIP / YAML de la demo | Los formatos de export ya están cerrados |

`aborted` y `failed` se distinguen con `GET /api/runs/{id}` después de la etapa SSE `failed`. El canvas no inventa un tercer estado.

## Dónde se construye

Fases 5 a 10 del plan de migración, dentro de `web/`. Esas fases ya están construidas. No se aplica a las plantillas Jinja.

El retoque de densidad y jerarquía, sin copiar las referencias de tablero, está en [v2-ui-refresh.md](v2-ui-refresh.md). Lo implementa `v2-ui-engineer`, no `ui-engineer`.

## Tema claro (TASK-35, 2026-10-05)

**Decisión de producto:** el tema oscuro sigue siendo el default. El operador elige System, Dark o Light en el pie del sidebar; la elección se guarda en `localStorage` (`mt-theme`). System sigue `prefers-color-scheme`.

**Mecánica:** `public/theme-init.js` es un script bloqueante servido desde `'self'` en el `<head>`. Pone `html[data-theme]` antes del primer paint, así que no hay parpadeo y la CSP no gana fuentes, hashes ni `unsafe-inline` nuevo. Los tokens claros se declaran en `globals.css` bajo `:root[data-theme="light"]` y, repetidos, bajo `@media (prefers-color-scheme: light) :root[data-theme="system"]`. Los nombres de token no cambian; ningún componente usa colores literales. Gráficos y mapa GPS leen los mismos tokens (`fill-mt-sev-*`, `stroke-mt-border*`).

**Paleta clara:**

| Token | Valor | Uso |
| :--- | :--- | :--- |
| `--mt-bg` / `--mt-surface` / `--mt-elevated` | `#f6f8fb` / `#ffffff` / `#eef2f7` | Lienzo, tarjetas, capas |
| `--mt-fg` / `--mt-muted` / `--mt-faint` | `#0f1a2a` / `#46566b` / `#56667a` | Texto (≥ 5,2:1 en las tres superficies) |
| `--mt-border-strong` | `#7b8ca2` | Bordes de inputs y chips (≥ 3,2:1) |
| `--mt-accent` / `--mt-accent-hover` / `--mt-focus` | `#0e7490` / `#0b5d73` / `#0b5d73` | Acción, enlaces, anillo de foco |
| Severidad (texto sobre fondo) | critical `#b4162a`/`#fde7ea`, high `#a84300`/`#ffeedd`, medium `#835600`/`#fff3d6`, low `#1d4ed8`/`#e4edff`, info `#3f4c5c`/`#eceff3`, unclassified `#56667a`/`#eef2f7` | Siempre con su etiqueta de texto |

**Contraste:** `web/src/components/shell/theme.test.tsx` comprueba AA en ambos temas (texto ≥ 4,5:1; foco y bordes de control ≥ 3:1; severidad sobre su fondo y sobre `surface` ≥ 4,5:1) y que los dos bloques claros sean idénticos. Para cumplirlo en oscuro, `--mt-border-strong` pasó de `#31465c` (2,0:1) a `#536a84` (≥ 3,1:1).
