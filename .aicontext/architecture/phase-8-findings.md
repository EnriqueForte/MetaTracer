# Fase 8 — findings

**Fecha:** 2026-09-29
**Estado:** Cerrada. La prosa del modelo y el feedback son la fase 9. Las descargas son la fase 10.

Cuando el run está `completed`, la página pide `GET /api/runs/{id}/findings` y conserva el orden del API. No recalcula severidad.

- Filtros en cliente: severity, tipo, confidence y búsqueda. Un `severity` null se muestra como Unclassified.
- Cero hallazgos es un resultado, distinto de un error de carga.
- La evidencia, el título y las URLs se pintan como texto. El enlace solo existe si `safeUrl` acepta `http` o `https`.
- El panel del finding muestra evidencia, campo, URLs y content type. No muestra justificación, impacto, remediación ni votos.

En una prueba local el run terminó sin hallazgos y la página mostró “No findings” junto a los filtros.
