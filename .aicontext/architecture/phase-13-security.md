# Fase 13 — revisión de seguridad de Web V2

**Fecha:** 2026-09-29
**Estado:** Cerrada. Veredicto del safety-guardian: **SIN BLOQUEANTES**.

El revisor recorrió `web/`, el rewrite de `/api` en `next.config.ts`, el bootstrap CSRF de `GET /api/auth/me` en `src/metatracer/api/app.py`, el job `web` de CI y el contexto Docker. No reabrió el pipeline.

## Checklist

Sin `dangerouslySetInnerHTML`, `innerHTML`, `eval` ni markdown a HTML. Los enlaces que salen del API pasan por `safeUrl`. El checkbox de scope nace desmarcado; el POST no manda las dos fuentes de scope ni `watch`. El navegador solo llama a `/api` del mismo origen. No hay `NEXT_PUBLIC_`. La CSP de producción no lleva `unsafe-eval` ni orígenes de terceros; `unsafe-eval` queda en `next dev`. La cookie de sesión no la lee JavaScript. Las mutaciones de `apiFetch` mandan `x-csrf-token`. El login sin cabecera sigue siendo 403 en el servidor. `package.json` pinnea versiones exactas. El `Dockerfile` no copia `web/`. `METATRACER_ALLOW_LOOPBACK` no se activa desde el frontend.

## Avisos que no son bloqueantes

Quedan escritos aquí. No son una aprobación condicional: el veredicto es sin bloqueantes, y estos puntos no abren red, scope ni XSS.

1. Los formularios de login, registro y setup hacen `fetch` propio en vez de `apiFetch`. Hoy mandan `credentials: "same-origin"` y `X-CSRF-Token`. El fallo sería una copia futura que olvide la cabecera; el servidor seguiría en 403.
2. Si el operador envía el login antes de que `GET /api/auth/me` deje la cookie CSRF, el header va vacío y el servidor responde 403. Es fail-closed.

## Cambio aplicado después del veredicto

`.dockerignore` excluye ahora el árbol `web/` y `spikes/web-v2-contract/` enteros, no solo `node_modules` y `.next`. El `Dockerfile` ya hacía `COPY` solo de `pyproject.toml`, `README.md` y `src/`. La exclusión evita que un `COPY .` futuro meta npm en la imagen.
