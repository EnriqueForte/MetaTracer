# R2 — dashboard

**Fecha:** 2026-09-29
**Estado:** Cerrada. Solo `web/`. Las plantillas de V1 no se tocaron.

La fila de arriba sigue siendo runs, findings, assets y tokens, con el mismo subtexto (completed/failed, unclassified, with issues, calls). Debajo, la severidad es una barra por color (`--mt-sev-*`), no acero. Los tipos y los dominios son un ranking con el acento. La evidencia repetida sigue en tabla, como texto. El uso del agente es una franja al pie, sin cifras grandes.

Si `runs.total` es 0 hay un solo párrafo. No hay ilustración ni un segundo botón de scan. No se pide ninguna cifra que `GET /api/stats` no traiga.

Vitest: color de critical y high, ranking de tipo en acero, snippet como texto, franja de agente y vacío con un solo enlace New scan.
