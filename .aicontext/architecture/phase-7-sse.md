# Fase 7 — SSE

**Fecha:** 2026-09-29
**Estado:** Cerrada. La tabla de findings sigue para la fase 8.

`/v2/runs/{id}` abre `EventSource` contra `/api/runs/{id}/stream` en el mismo origen. Al desmontar la página se cierra el stream. Eso no cancela el scan. No hay botón de abortar.

- Las siete etapas y el mensaje se pintan como texto. Un evento que no encaja se ignora.
- `completed` cierra el stream y vuelve a leer el run.
- La etapa SSE `failed` también cierra el stream. `aborted` o `failed` salen del `status` del GET, no de la etapa.
- Si el socket cae, polling del GET cada 2 s hasta `completed`, `failed` o `aborted`.
- Un 404 no se reinterpreta como scan fallido.

En una prueba local el run terminó en estado `completed` con cero assets y la página mostró ese estado, sin lista de hallazgos.
