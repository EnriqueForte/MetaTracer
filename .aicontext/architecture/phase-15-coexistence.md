# Fase 15 — convivencia

**Fecha:** 2026-09-29
**Estado:** Cerrada. `/` sigue en FastAPI. `/v2` es opt-in. No hay corte.

## Qué ve el operador

En el shell de Web V2, con sesión iniciada, el texto fijo es: “Signing out also ends the session used by the classic UI.” El logout sigue siendo `POST /api/auth/logout` con CSRF. La cookie es `Path=/`, así que en el mismo origen cierra también la sesión de la UI clásica.

El pie tiene un enlace `Classic UI` con `href="/"`. Es un `<a>`, no un `Link` de Next, para que `basePath` no lo convierta en `/v2`.

Las plantillas de V1 no se tocaron. No hay enlace nuevo en Jinja: sin el proxy, `/v2` en el puerto de Uvicorn no existe, y un enlace ahí sería un 404 en el arranque por defecto.

## Cómo compararlas en un solo origen

Tres procesos, ninguno sustituye al otro:

1. Uvicorn en `127.0.0.1:8000` (`metatracer serve` o el contenedor actual).
2. `npm run build` y `npm run start -- --hostname 127.0.0.1 --port 3000` dentro de `web/`, con `METATRACER_API_ORIGIN` apuntando a ese Uvicorn si además se abre Next directo.
3. `npm run coexist` dentro de `web/`. Escucha en `127.0.0.1:8080`.

`http://127.0.0.1:8080/` es la UI clásica. `http://127.0.0.1:8080/v2` es Web V2. `/api` y `/static` van a Uvicorn, no a Next. El puerto se cambia con `METATRACER_COEXIST_PORT`. Los upstreams, con `METATRACER_API_ORIGIN` y `METATRACER_V2_ORIGIN`, y solo aceptan `http` en `127.0.0.1` o `::1`.

El proxy no entra en la imagen Python ni en Compose. El servicio `web` de Compose sigue siendo Uvicorn en el puerto 8000. Quitar el proceso del proxy es el rollback: `/` no se mueve.

El `Host` que ve FastAPI es el del navegador (`127.0.0.1:8080`), no el del upstream. Si no, `url_for` escribe el CSS como `http://127.0.0.1:8000/static/...` y la CSP de la página (`style-src 'self'`) lo bloquea: la UI clásica sale en blanco. El login no lo sufre porque sus hojas van a `/static/...` relativo.

## Qué no es

No se enruta `/` a Next. No hay `/legacy`. No se borra ninguna plantilla. El corte sigue exigiendo otro ADR. Setup sigue en `in_progress` y el Playwright contra Uvicorn sigue sin hacerse.

## Revisión

El safety-guardian no encontró bloqueantes en el proxy: bind en loopback, sin log de la cookie, sin CORS, sin `METATRACER_ALLOW_LOOPBACK`.

Tests: Vitest del shell (frase de sign out y `href="/"`) y `node --test` del enrutado, incluido un reenvío real de `/` y `/v2` a dos servidores locales. No se levantó el par Uvicorn + Next en el navegador en este checkpoint.
