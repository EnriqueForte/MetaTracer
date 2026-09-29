# R5 — history, scopes, users

**Fecha:** 2026-09-29
**Estado:** Cerrada. Solo `web/`. Las plantillas de V1 no se tocaron.

Las tres listas usan el mismo ritmo que la tabla de evidencia del dashboard: cabecera en caja de frase, `py-1`, filas `py-1.5`. History conserva estado (incluido `aborted`), target, assets, findings y fecha. Scopes conserva nombre, descripción, dominios y el recuento. Users conserva usuario, rol y la acción. Invitations conserva rol y estado. No hay columnas nuevas.

El código de invitación sigue en un solo nodo de texto y se quita al descartarlo. No entra en la tabla.

Vitest: cabecera densa e `aborted` en history, dominios como texto en scopes, y el código de invitación una sola vez.
