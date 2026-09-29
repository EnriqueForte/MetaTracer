# Web V2 — consola de analytics

**Fecha:** 2026-09-29
**Estado:** fases 1–7 aplicadas en `web/`. La revisión de seguridad del diff queda como cierre.
**Alcance:** solo `web/`. Jinja, API, CLI y contratos no se tocan.

Este documento sustituye la paleta de acero de [v2-visual-direction.md](v2-visual-direction.md) para Web V2. Siguen vigentes: no inventar cifras, no renderizar HTML de datos del target, no añadir páginas (knowledge, webhooks, watch, chat, settings) y no mover validaciones de seguridad al cliente.

## Stack comprobado

Next.js 16.3.6, React 19.3.0, TypeScript 5.9.3, Tailwind CSS 4.3.3 (`@theme inline` sobre variables `--mt-*`). Primitivos al estilo shadcn (CVA, Radix Slot/Dialog, `clsx`, `tailwind-merge`) en `web/src/components/ui/`. Iconos: `lucide-react`. No hay shadcn CLI, ni TanStack Query, ni librería de gráficos. El fetch es `apiFetch` + `useEffect`. El progreso de un run usa `EventSource` nativo.

## Agentes

`ui-architect` y `ui-engineer` siguen siendo de Jinja: su mandato prohíbe React. No se usan para este rediseño.

`v2-ui-engineer` es el dueño de `web/`, pero su prompt de R1–R6 prohíbe donuts y dependencias npm, y fija el acero como único acento. Este encargo lo sustituye en paleta y en gráficos. La implementación de la fase 1 se hace sobre ese código, sin reabrir la migración.

`test-engineer` valida la suite de `web/` al cerrar las fases de UI. `safety-guardian` revisa la superficie final (HTML no confiable, `safeUrl`, CSP, dependencias nuevas). Recharts, si entra en la fase 4, es dependencia nueva y pasa por esa revisión antes de instalarse.

## Tokens

Viven en `web/src/app/globals.css`. Los nombres `--mt-*` no cambian, así las utilidades existentes heredan la paleta. Nuevos: secundario, cinco colores de serie (`--mt-chart-1`…`5`), radio de tarjeta, sombra plana, duración y easing.

Severidad (texto y relleno de gráfico), siempre con etiqueta:

| Nivel | Token | Uso |
| :--- | :--- | :--- |
| Critical | `--mt-sev-critical` | Rojo intenso |
| High | `--mt-sev-high` | Naranja |
| Medium | `--mt-sev-medium` | Ámbar |
| Low | `--mt-sev-low` | Azul |
| Info | `--mt-sev-info` | Pizarra |

El acento de acción es cian (`--mt-accent`). El azul (`--mt-secondary`) es señal secundaria, no el fondo de la navegación.

## Datos reales del dashboard

`GET /api/stats` aporta runs, findings (total, unclassified, `severity_breakdown`, `by_type`), assets, `top_domains`, `top_evidence` y `agent_usage`. No hay severidad ni target en `top_evidence`. No hay serie temporal.

`GET /api/runs` trae `started_at`, pero la lista está paginada. Ver «Actividad temporal».

## Fases

1. Tokens y bases — hecha.
2. Shell — hecha. Sidebar con icono Lucide, activo en cian suave, topbar con el aviso corto y el estado derivado de `GET /api/auth/me` (alcanzable o no). La campana que ya existía se queda.
3. KPI — hecha. Scans, findings, assets y uso de IA, con los contadores reales. `with_issues` se etiqueta «With issues»: son extracciones que no quedaron en `ok`, no assets con findings.
4. Gráficos — hecha en SVG propio (donut de severidad y barras de tipo). Recharts no está instalado; cinco segmentos no justifican una dependencia nueva. La severidad no clasificada sigue en el anillo porque el total la incluye.
5. Dominios y evidencia — hecha. El conteo de dominio no se renombra a «assets» ni «expuestos»: el API cuenta hosts de scope y de URL. La evidencia no trae severidad ni target, así que la tabla no inventa esas columnas. El snippet es un nodo de texto.
6. Responsive y foco — aplicado en el grid del dashboard (1 / 2 / 4 columnas), overflow de la tabla, `prefers-reduced-motion` y anillo de foco ya existente.
7. Tests de `web/` — la suite cubre color de severidad, donut, evidencia hostil y el shell.
8. Revisión de seguridad — sin bloqueantes. Evidence, dominios y notificaciones siguen siendo texto. Sin dependencia nueva y sin relajar la CSP.

## Actividad temporal

`GET /api/stats` no trae serie. `GET /api/runs` sí trae `started_at` y `total_findings`, pero paginado. Pintar solo la primera página mentiría el histórico, y recorrer todas las páginas en el dashboard no es el contrato de esa pantalla. No hay gráfico de actividad. Si más adelante el stats incluye buckets por día, se puede añadir sin datos ficticios.
