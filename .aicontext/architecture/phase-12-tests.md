# Fase 12 — tests de Web V2

**Fecha:** 2026-09-29
**Estado:** Cerrada en el job de CI y en Vitest. El Playwright contra el API real queda abierto.

## Qué corre

- `npm test` en `web/`: Vitest 5.0.2, jsdom, Testing Library. Nueve tests.
  - `safeUrl`: http/https se aceptan; `javascript:`, `data:` y vacío se rechazan.
  - Snippet `<script>` y prosa del modelo se pintan como texto. Una URL `javascript:` no es un enlace. Una URL https sí.
  - `severity: null` se muestra como Unclassified.
  - Lista vacía y error de carga no se confunden.
  - El botón de confirmar el scope sigue deshabilitado hasta el checkbox.
  - HTTP 403 y 409 del POST se muestran como texto.
- `npm run test:e2e`: Playwright 1.63.0, Chromium, contra `next start` en `127.0.0.1:3456`. Un test: el modal no confirma hasta el checkbox. El rewrite de `/api` apunta a `127.0.0.1:8765` porque el build hornea `METATRACER_API_ORIGIN`. Sin FastAPI en ese puerto el proxy responde `ECONNREFUSED`; el gate del modal no depende de esa respuesta.
- Job `web` en `.github/workflows/ci.yml`: `npm ci`, `npm test`, `npm run build` con `METATRACER_API_ORIGIN=http://127.0.0.1:8765`, Playwright Chromium, `npm run test:e2e`. No toca los jobs de Python.
- pytest `-m "not e2e"`: 682 passed, 5 skipped, 4 deselected. Una corrida anterior falló `test_defaults` porque `METATRACER_DATABASE_URL` apuntaba a una base de un servidor de preview. Con el entorno limpio el test pasa. No es un cambio de producto.

## Qué no cubre este checkpoint

La arquitectura pide Playwright contra Uvicorn de test y `tests/fixtures/mock_origin.py`, con `METATRACER_ALLOW_LOOPBACK` solo en ese proceso: wizard hasta el 202, página de run, auth encendida y apagada, un viewer que no completa un POST, y al menos un evento SSE de etapa más uno terminal (o el polling si se corta el stream). También pide el fixture hostil a través del API, no solo un `fetch` simulado.

Eso no está en `web/e2e/`. No cuenta como paridad verificada. No sustituye la fase 13. Sí queda pendiente antes de cualquier conversación de corte.

## Pins

Sin caret. Añadidos como devDependencies: `vitest` 5.0.2, `jsdom` 30.1.1, `@testing-library/react` 16.3.3, `@testing-library/jest-dom` 7.0.1, `@playwright/test` 1.63.0, `@vitejs/plugin-react` 6.1.1. `typescript` sigue en 5.9.3.
