# Fase 9 — análisis del modelo y feedback

**Fecha:** 2026-09-29
**Estado:** Cerrada. Las descargas del reporte son la fase 10.

En el mismo panel del finding, debajo de la evidencia:

- Justificación, impacto, pasos de reproducción y remediación. Solo si el API los trae. Cada uno es texto, no HTML.
- El bloque se titula “AI analysis — not evidence”.
- Feedback como en V1: el operador elige otra severidad; el voto `up` o `down` se deriva de si sube o baja en `info → critical`. El servidor vuelve a validar la dirección. Un hallazgo sin severidad no se corrige en cliente: el 422 se muestra como texto.
- Alta y borrado: `PUT` y `DELETE /api/feedback/{id}`, con CSRF.

No se comprobó el panel con un hallazgo real: el scan local de prueba no produjo findings. El build sí incluye la sección.
