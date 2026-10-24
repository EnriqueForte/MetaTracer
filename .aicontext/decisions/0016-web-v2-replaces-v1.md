# ADR-0016: Web V2 sustituye a Web V1

**Fecha:** 2026-10-24  
**Estado:** Aceptada (T11 completo: commits 844627d, 57320ab, 8cfdbd8)  
**Ámbito:** capa Web. No toca pipeline, detectores, agentes LLM, safety core ni base de datos.  
**Relacionada:** [ADR-001](../architecture/ADR-001-nextjs-react-migration.md) (abrió el
programa y exigió que el corte fuera un ADR aparte — este es ese ADR).

## Contexto

ADR-001 autorizó Web V2 como cliente **paralelo** de Web V1, con una condición explícita:
«Un big-bang que apague `/` de FastAPI el mismo día que exista el primer componente React»
estaba prohibido, y el corte requeriría un ADR propio con la matriz de paridad en `migrated`.

Desde entonces:

- La [matriz de paridad](../migrations/feature-parity-matrix.md) cerró **todas** sus filas
  en `verified` (la última, Setup, en T9), sin ninguna en `missing`.
- El stack de despliegue con dos servicios y un origen único quedó probado en Docker (T10):
  routing, cookies, login y SSE real a través de Caddy.
- La duplicación ya tenía coste medido: el bug de CSRF de MIN-01 existía en **ambas**
  superficies y hubo que arreglarlo dos veces (T1). Cada cambio de UI se implementaba,
  probaba y revisaba por duplicado.

El producto **no está en producción**, así que el corte no arriesga usuarios reales.

## Decisión

**Web V2 es el frontend del producto. Web V1 se retira.**

1. **Un solo origen, servido por Caddy** (`deploy/Caddyfile`): `/api/*` y `/static/*` →
   FastAPI; todo lo demás → Next.js. La cookie de sesión es `SameSite=Lax` y la CSP
   `connect-src 'self'`, así que un segundo origen exigiría CORS y un modelo de sesión más
   débil: se descarta.
2. **FastAPI es API-only.** No renderiza HTML: se eliminaron `api/pages.py`, las diez
   plantillas Jinja, los cuatro assets de `/static` y `tailwind.input.css`.
3. **Next.js sirve desde la raíz** (`basePath: /v2` eliminado). La constante `BASE_PATH`
   queda como cadena vacía para no romper el compositor de URLs.
4. **La imagen Python no gana Node.** Web V2 es un servicio aparte (`web/Dockerfile`,
   `output: 'standalone'`); `.dockerignore` sigue excluyendo `web/`.
5. **Gobernanza:** `v2-ui-engineer` pasa a ser el único dueño de la interfaz de navegador;
   `ui-engineer` queda para CLI + API. Los contratos de `.aicontext/ui/` que describen Jinja
   son históricos.

## Alternativas descartadas

- **Mantener V1 en `/classic` durante un release.** Se consideró como red de seguridad, pero
  el producto no está en producción: el coste de arrastrar el código (y su doble
  mantenimiento) no compra nada. Un `git revert` es la red real.
- **Servir Next desde FastAPI (`output: 'export'` estático).** Rompe el SSR y las rutas
  dinámicas (`/runs/[runId]`), y obliga a revisar la app entera.
- **Next y FastAPI en el mismo contenedor.** Mete toolchain Node en una imagen que se diseñó
  mínima a propósito (ADR-001, supply chain).
- **Cortar sin verificar en Docker.** Fue precisamente lo que la validación evitó: el
  Caddyfile inicial **no arrancaba** (primera línea sin `#`), algo invisible en los tests
  unitarios.

## Consecuencias

- **Despliegue:** tres servicios (web, web-v2, proxy). `web` ya no publica puerto; el proxy
  es la única entrada. `docker compose up` levanta todo el producto.
- **Tests:** se retiraron 718 líneas de tests de plantillas y 7 tests de página; los helpers
  que obtenían el CSRF de `GET /login` usan ahora `GET /api/auth/me` (ADR-0015), aceptando el
  401 del visitante anónimo. Suite: **755 passed, 6 skipped**; cobertura **91.30%**.
- **Seguridad:** el doble-submit y las cabeceras de seguridad no cambian; la CSP del shell
  vive en `web/next.config.ts` y la de la API en `api/security_headers.py`.
- **Riesgo residual:** un fallo de Next deja el producto sin UI (el API y la CLI siguen
  funcionando). Se acepta por no estar en producción y porque el rollback es un `git revert`.
- **Medición del beneficio:** −4365 líneas de código y un único frontend que mantener.

## Verificación

- `docker compose up`: routing (`/`, `/login`, `/dashboard` → Next), `/api/health` → FastAPI.
- Flujo completo por el proxy: CSRF → login → mutación → **SSE streameado** (2103 bytes).
- `caddy validate`: configuración válida.
- La imagen Python no contiene `pages`, `templates` ni `static`.
- `pytest` 755 passed · `ruff` limpio · Vitest 83 · Playwright (wizard + auth) en CI.
