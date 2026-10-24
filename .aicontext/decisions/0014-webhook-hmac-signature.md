# ADR-0014: Webhooks firmados con HMAC y secreto en claro

**Fecha:** 2026-10-03  
**Estado:** Aceptada (v3.2 / [TASK-27](../tasks/27-security-hardening-p0.md), P0-3)  
**Slice:** Hardening post-auditoría

## Contexto

`WebhookConfig.signature_secret` existía pero **no firmaba nada**: solo se
persistía `SHA-256(secret)`. El receptor no tenía forma de verificar que la
entrega venía de MetaTracer, así que cualquier tercero que conociera la URL
podía inyectar eventos falsos ("scan completed, 0 findings") y, peor, el
operador creía tener integridad cuando no la tenía.

Un hash no puede firmar: HMAC necesita la clave, no su digest.

## Decisión

- Se persiste el **secreto en claro** en `signature_secret` (`Text`), con el
  mismo tratamiento que `headers` (que ya guardaban tokens).
- La entrega firma los **bytes exactos** que envía:
  `sha256=<hex(HMAC-SHA256(secret, "{timestamp}.{body}"))>`, con el cuerpo
  serializado una sola vez (JSON compacto, claves ordenadas).
- Cabeceras: `X-MetaTracer-Timestamp` (unix s) y `X-MetaTracer-Signature`.
- El secreto **nunca** se devuelve por la API. `GET /api/webhooks` reporta
  `signature_status`: `active` | `needs_secret` | `none`.
- Filas legacy (solo hash) se entregan **sin firmar** con warning hasta que el
  operador vuelva a introducir el secreto.

## Alternativas descartadas

- **Cifrar el secreto en reposo con `cryptography`.** Añade una dependencia
  nativa a una lista cerrada para proteger un secreto que ya vive junto a los
  `headers` del webhook; el modelo de amenaza no cambia (mismo acceso a la BD).
- **Firmar el hash en lugar del secreto.** No es verificable por el receptor:
  no conoce el hash ni puede recalcularlo desde el cuerpo.
- **Guardar el secreto solo en memoria.** Se pierde en cada reinicio y las
  entregas pendientes (relay buffer) dejarían de poder firmarse.

## Consecuencias

- El receptor debe verificar contra **los bytes crudos** del body (no
  re-serializar) y rechazar timestamps fuera de una ventana (5 min sugerido).
- Un leak de la base de datos expone los secretos de webhook: riesgo asumido y
  documentado (mismo nivel que los `headers`).
- Rotar el secreto es un `PUT`; las entregas ya encoladas usan el payload
  cacheado y se firman con el secreto vigente en el momento del envío.

**Verificación:** `tests/unit/test_webhook_dispatcher.py`,
`tests/integration/test_api_webhooks.py`, sección "Webhook signatures" del README.
