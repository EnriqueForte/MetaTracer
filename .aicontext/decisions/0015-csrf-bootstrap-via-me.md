# ADR-0015: `/api/auth/me` es el bootstrap del token CSRF

**Fecha:** 2026-10-23  
**Estado:** Aceptada (v3.2 / fix MIN-01, sin task propia)  
**Slice:** Corrección post-auditoría

## Contexto

El double-submit de CSRF necesita que el cliente **lea** el token que el
servidor puso en la cookie `csrf_token` y lo devuelva en `X-CSRF-Token`. En las
páginas Jinja (V1) el servidor inyecta `<meta name="csrf-token">` y el JS lo
lee de ahí.

Web V2 es una app Next.js que **no renderiza** ese meta, así que leía la cookie
con `document.cookie` — que **no es una API del navegador** (solo existe como
shim en jsdom). En un navegador real todas las mutaciones de V2 con auth activa
fallaban con 403 CSRF, incluido el login.

## Decisión

`GET /api/auth/me` es el canal de bootstrap del token, en las dos ramas:

- **200 autenticado**: `csrf_token` en el cuerpo JSON.
- **401 sin sesión**: `X-CSRF-Token` en la cabecera de respuesta.

En ambos casos el endpoint **emite la cookie pre-sesión** si no existía
(mint único, retirado del middleware para no enviar dos `Set-Cookie`
distintos). V2 persiste el valor en `<meta name="csrf-token">` al resolver la
sesión, y `apiFetch` lo lee de ahí en cada mutación.

El invariante de seguridad **no cambia**: el servidor sigue comparando header y
cookie con `hmac.compare_digest`. Exponer el mismo valor en el cuerpo no
debilita el control (un atacante cross-origin no puede leer la respuesta), y con
XSS la protección de CSRF cae igual con o sin el meta.

## Alternativas descartadas

- **Leer la cookie con `document.cookie`.** No es una API real; funcionaba en
  jsdom y por eso los tests no lo detectaban.
- **Añadir un endpoint `/api/auth/csrf` dedicado.** Duplica un round-trip que
  V2 ya hace en cada arranque de sesión.
- **Desactivar CSRF para las rutas de V2.** Renuncia al control para resolver un
  bug de transporte.
- **Exigir el meta también en V2 desde el servidor.** Next no controla el HTML
  de FastAPI; el token tendría que viajar por otro canal de todas formas.

## Consecuencias

- V1 y V2 obtienen el token por el mismo mecanismo (meta), con un solo camino
  de lectura en el cliente.
- `tests/integration/test_api_auth.py` cubre las dos ramas; el e2e de auth
  (`playwright.auth.config.ts`) reproduce el flujo real login + mutación.
- Un cliente API sin navegador (curl, CI) obtiene el token por cabecera o cuerpo
  sin depender de cookies legibles por JS.

**Verificación:** `tests/integration/test_api_auth.py`,
`web/e2e/auth.spec.ts`, `web/src/lib/api/browser.test.ts`.
