# Fase 6 — wizard y scope

**Fecha:** 2026-09-29
**Estado:** Cerrada. El progreso del run sigue sin implementarse.

Reconnaissance (`/v2`) es el wizard de `index.html`:

- Targets, scopes guardados o dominios manuales, profundidad `brief` | `standard` | `detailed`.
- El scope no se deduce del target. No se envía `watch`.
- Si hay scopes guardados marcados, el POST lleva solo `scope_ids`. Si no, solo `scope_domains`. Nunca los dos.
- `scope_confirmed: true` solo después del modal. El checkbox nace desmarcado. Cancel tiene el foco al abrir. Escape cierra. El botón de confirmar está deshabilitado hasta el check.
- 202 navega a `/v2/runs/{run_id}`. Esa ruta aún no muestra el SSE: dice que el progreso no está disponible. Es la fase 7.
- Textos de 403, 404, 409, 429 y 500 iguales a V1.

El modal enseña los dominios que realmente viajan en el POST. En V1, si solo se elegían scopes guardados, esa línea podía quedar vacía porque leía el campo manual.
