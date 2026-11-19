# TASK-55: Grafos en vivo en el scan

**Módulo:** `extractors/ingest.py`, `db/models.py`, `services/graph.py`, `api/workspace.py`, `web/` (canvas)  
**Spec:** [specs/55-scan-live-graph.md](../../specs/55-scan-live-graph.md)  
**Dependencias:** TASK-01, TASK-36, TASK-43, TASK-47, TASK-51  
**Agentes:** `pipeline-engineer`, `v2-ui-engineer`; veto `safety-guardian`  
**Estado:** **Cerrada 2026-11-19.**

## 1. Objetivo técnico

Persistir aristas de descubrimiento, exponer `GET /api/runs/{run_id}/graph` y
montar en la ficha del run Apache ECharts (métricas) + Cytoscape.js (redes)
bajo CSP de producción sin `unsafe-eval` y sin CDN.

## 2. Subtareas

- Enums `graph_node.kind` y `discovery_edge.kind` en contratos y modelo.
- Tabla `discovery_edge`; Alembic Postgres; SQLite `create_all`.
- Escritura en crawl (`FetchedPage` hijos) y en `_execute_local` (estrella).
  Un fallo de persistencia se loguea y el run sigue.
- Endpoint de lectura: crawl + correlaciones derivadas (bipartito asset↔valor)
  + métricas `by_content_type` / `by_finding_type` / `by_extraction_status`.
  Techo 400/800; `truncated`. Sin `evidence_snippet`.
- npm `echarts` y `cytoscape` versión exacta, `--ignore-scripts`. Wrappers
  propios `'use client'` + `next/dynamic({ ssr: false })`. Cero
  `echarts-for-react` / `react-cytoscapejs` / extensiones Cytoscape.
- Canvas en `RunProgress`; poll 2 s; tooltips texto; `safeUrl()`; `animate: false`.

## 3. Supply chain (web)

| Paquete | Licencia | Por qué |
| :--- | :--- | :--- |
| `echarts` | Apache-2.0 | Barras de MIME / tipo de hallazgo / estado de extracción. Import modular (`echarts/core` + `BarChart` + `CanvasRenderer`). |
| `cytoscape` | MIT | Red crawl y correlación. Core only. Layout `breadthfirst` / `cose` con `animate: false`. |

No se relaja `web/next.config.ts` ni `security_headers.py`. Si ECharts viola
CSP en `next build`, se recorta el chart.

Limitaciones aceptadas (safety-guardian, 2026-11-19, PASS-WITH-LIMITATIONS):
`new Function` vive solo en `GeoJSONResource` (series map/graph OOS; el
wrapper registra `BarChart` + `CanvasRenderer`). CI y `web/Dockerfile`
siguen `npm ci` sin `--ignore-scripts`, mismo patrón que TASK-35: ni
`echarts` ni `cytoscape` tienen `postinstall` de consumidor; un flag
global rompería binarios nativos de Next/esbuild.

## 4. Fuera de alcance

Mapas, OSINT de identidad, cambiar `ProgressEvent`, CLI, tiles, ZIP/HEIC.

## 5. DoD

- [x] Enums en `tasks/README.md` y `data-contracts.mdc`
- [x] Edges persistidos en HTTP y local; unique `(run_id, from_url, to_url, kind)`
- [x] `GET /api/runs/{id}/graph` con techo y `truncated`
- [x] UI en ficha del run; wizard sin canvas
- [x] Vitest + unit/integration; ruff; CSP sin `unsafe-eval` en producción
- [x] Spec 55 closed; MEMORY y backlog actualizados
