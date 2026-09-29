# Fase 5 — shell

**Fecha:** 2026-09-29
**Estado:** Cerrada. Las pantallas de datos siguen vacías a propósito.

El marco de `web/` repite `base.html`:

- Skip link a `#main-content`.
- Nav: Dashboard, Reconnaissance, History, Scopes. Users solo si la auth está apagada o el rol es `operator`.
- Aviso ético y pie de pasivo, en inglés, con el texto de V1.
- Campana: `GET /api/notifications` y `DELETE` por índice. El target y el error se pintan como texto. `aborted` tiene su badge.
- Sign out solo con sesión: `POST /api/auth/logout` con `x-csrf-token` leído de la cookie, luego `/v2/login`.
- Login, register y setup no tienen sidebar ni campana.

`/api/auth/me` distingue auth apagada (`200`, `authenticated: false`) de sesión ausente (`401`, que manda al login). El tipo generado de auth sigue abierto; el shell valida la forma antes de mostrarla.

La versión `0.6.0` junto a la marca es la de `metatracer.__version__`. Health no la devuelve.

Dashboard, History, Scopes, Users y Reconnaissance dicen que la pantalla aún no está. El wizard es la fase 6.
