# Spec 55 — Grafos en vivo en el scan

**Estado:** closed  
**Agente previsto:** `pipeline-engineer` (persistencia + API) · `v2-ui-engineer` (canvas) · `ui-architect` (contrato visual, ya emitido en design-system §9) · `safety-guardian` (deps npm + CSP)  
**Skill al abrir:** `metatracer-ui` + `metadata-extraction` + `metatracer-supply-chain`  
**Task:** [.aicontext/tasks/55-scan-live-graph.md](../.aicontext/tasks/55-scan-live-graph.md)  
**Enums:** `.aicontext/tasks/README.md` → `graph_node.kind`, `discovery_edge.kind`

## Intención

Cuando un scan ya tiene `run_id` (POST 202 → `/runs/{id}`), el operador ve
conexiones reales: de qué página in-scope salió un documento, qué activos
comparten un valor, y cómo se llena el inventario. Un grafo sin esas preguntas
sigue prohibido.

El wizard vacío no muestra canvas: no hay dato.

## Alcance

- Persistir aristas de descubrimiento (`discovery_edge`) en crawl HTTP y en
  ingesta local (estrella `file:` raíz → ficheros).
- `GET /api/runs/{run_id}/graph`: crawl + correlaciones derivadas + métricas.
  Techo 400 nodos / 800 aristas por capa; `truncated`.
- UI en `RunProgress`: ECharts (métricas) + Cytoscape.js (redes), empaquetados,
  client-only, cero CDN. Poll 2 s mientras el run no es terminal.
- SSE `ProgressEvent` intacto.

## Fuera de alcance

Mapas/tiles, grafo OSINT de identidad, CVSS, chat, ZIP/HEIC, segundo SSE,
extensiones Cytoscape, series `graph`/`map` de ECharts, CLI con grafo,
quedarse en `/` sin redirigir.

## Dependencias

Specs 36/43 (correlación como valor, no identidad), 47 (workspace), 51 (local),
52 (pulido). Contrato [design-system-v2.md](../.aicontext/ui/design-system-v2.md) §9.
