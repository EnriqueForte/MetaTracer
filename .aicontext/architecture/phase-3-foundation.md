# Fase 3 — fundación Web V2

**Fecha:** 2026-09-26
**Estado:** Cerrada. `src/metatracer/`, `pyproject.toml` y el Dockerfile no cambiaron.

## Lista cerrada

Directas, sin rangos, en `web/package.json`:

| Paquete | Dónde |
| :--- | :--- |
| `next@16.3.6` | runtime de `web/` |
| `react@19.3.0` | runtime |
| `react-dom@19.3.0` | runtime |
| `typescript@5.9.3` | dev. No 7.x: `openapi-typescript@7.13.0` exige `typescript@^5` |
| `@types/react@19.3.0` | dev |
| `@types/react-dom@19.3.0` | dev |
| `@types/node@24.19.0` | dev |
| `openapi-typescript@7.13.0` | dev. No se importa desde la UI |

`npm run generate:api` escribe `web/src/lib/api/generated/schema.d.ts` desde el snapshot de la fase 2. Tailwind, shadcn, Lucide, TanStack Query y Zod no están.

La imagen Python sigue copiando solo `pyproject.toml`, `README.md` y `src/`. `.dockerignore` excluye `web/node_modules` y `web/.next`.

## Qué hay

- App Router en `web/`, `basePath: '/v2'`.
- Una página estática: “Web V2 foundation”. Sin wizard, sin findings, sin `dangerouslySetInnerHTML`.
- `METATRACER_API_ORIGIN` solo en servidor. Por defecto `http://127.0.0.1:8000`. No es `NEXT_PUBLIC_` y no sale del request.
- Rewrite `beforeFiles` de `/api/:path*` hacia ese origen, con `basePath: false`, para que `/api` no quede bajo `/v2`.
- `NEXT_TELEMETRY_DISABLED=1` al cargar `next.config.ts`.

## CSP medida en `next build` + `next start`

El HTML de producción carga scripts solo desde `/v2/_next/static/…`. No hay origen de terceros ni `unsafe-eval`.

Sí hay scripts inline de hidratación (`self.__next_f.push`). Por eso la CSP de producción lleva `script-src 'self' 'unsafe-inline'`. `style-src` también lleva `'unsafe-inline'` por atributos `style` del propio Next. `next dev` añade `'unsafe-eval'` solo en desarrollo, por React Refresh.

La CSP de FastAPI no se tocó. Las respuestas de `/api` que atraviesan el rewrite conservan la cabecera del API, sin `unsafe-eval`.

## Proxy, comprobado

Contra `next start` (el destino queda grabado en el build) y un FastAPI en `127.0.0.1`:

- `GET /api/health` a través de Next devuelve `{"status":"ok"}`.
- `POST /api/auth/login` devuelve `Set-Cookie` de `metatracer_session` (HttpOnly, `SameSite=lax`, `Path=/`) y de `csrf_token`.
- `POST /api/runs` devuelve 202.
- `GET /api/runs/{id}/stream` responde `text/event-stream`, reenvía `X-Accel-Buffering: no` y los primeros `data:` llegan en la misma lectura, sin esperar al cierre.

El destino del rewrite se fija al ejecutar `next build`, leyendo `METATRACER_API_ORIGIN` en ese momento. `next dev` lo lee al arrancar el servidor de desarrollo. Cambiar la variable solo en `next start`, sin reconstruir, no mueve el upstream.

La cookie CSRF previa a la sesión la emite hoy `GET /login` de Web V1, que este rewrite no cubre. El login de Web V2 (fase 11) tiene que obtenerla en el mismo origen. El `Set-Cookie` del POST de login, que es el que crea la sesión, ya atraviesa el rewrite.
