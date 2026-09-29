# R4 — wizard

**Fecha:** 2026-09-29
**Estado:** Cerrada. Solo `web/`. Las plantillas de V1 no se tocaron.

Targets, scope, profundidad y Start scan están en una franja. Ya no hay cuatro bloques numerados. El scope no se deduce del target. Si hay scopes guardados marcados, el POST sigue llevando solo `scope_ids`; si no, solo `scope_domains`.

El modal no cambió de lógica: el checkbox nace desmarcado, Cancel toma el foco, Escape cierra y confirmar sigue deshabilitado hasta el check. Los textos de 403, 404, 409 y 429 son los de antes.

Vitest: checkbox desmarcado y los cuatro códigos HTTP como texto.
