---
name: metatracer-ui
description: Stack y reglas de la Web UI de MetaTracer (Next.js/React en web/, tokens .mt-*, Tailwind 4, TanStack Query, renderizado seguro sin dangerouslySetInnerHTML, safeUrl, cabeceras CSP de next.config.ts) y la superficie API que la sirve (FastAPI solo-API desde T11). Usar al trabajar en web/, api/, cli/, services/ o deploy/, y al implementar o revisar cualquier cambio de interfaz.
---

# UI de MetaTracer — stack y seguridad

Cubre las amenazas 10, 11, 12 y 15 del modelo de amenazas ([.agents/agents.md](../.agents/agents.md)).
Fuentes: `.aicontext/tasks/06-interfaces.md`, `20-ui-polish.md`, `26-ui-redesign.md`,
`35-ui-ux-improvements.md` y `.aicontext/ui/`.

**Principio:** la UI es donde el safety se hace visible y donde el contenido del target se
renderiza. El renderizado como texto y la ausencia de CDN son tan inviolables como el
wrapper HTTP.

## Stack real (tras T11)

- **Web V2 es el frontend del producto** y sirve desde la raíz del origen.
  **Web V1 (Jinja + Alpine) fue retirada en T11**: no quedan plantillas, ni
  `api/pages.py`, ni `/static` de V1. FastAPI es **solo-API**.
- React 19 + Next.js 16 (App Router) en `web/`, TypeScript estricto.
- Tailwind **4.3.3** compilado en el build de Next; tokens `.mt-*` como CSS
  variables en `web/src/app/globals.css`.
- **TanStack Query** para datos de servidor y **Zod** en las fronteras de
  formulario (advisory: Pydantic sigue siendo la autoridad).
- Primitivas Radix + Lucide, empaquetadas en el bundle. **Cero CDN.**
- Un solo origen (`deploy/Caddyfile`): `/api/*` → FastAPI, resto → Next. La
  cookie de sesión es `SameSite=Lax` y la CSP `connect-src 'self'`.
- Wizard (TASK-51): modo carpeta local envía `local_paths` (rutas **en el
  servidor**, texto). No hay upload de bytes ni `<input type="file">`.
- Grafos (TASK-55): `echarts` y `cytoscape` empaquetados, wrappers propios
  client-only, `next/dynamic({ ssr: false })`. Cero CDN, cero `echarts-for-react`
  / `react-cytoscapejs`. Tooltips texto; `safeUrl()`; `animate: false`. El
  canvas vive en la ficha del run, no en el wizard.

## Reglas de renderizado (inviolables)

El target escribe `evidence_snippet`; el modelo escribe
`severity_justification`, `impact_analysis`, `remediation_advice`,
`reproduction_steps` y `title`. **Los dos son hostiles.**

- **Prohibido** `dangerouslySetInnerHTML`, cualquier markdown-a-HTML y cualquier
  equivalente de `|safe` / `x-html`. Todo dato va como **nodo de texto**.
- URLs solo `http`/`https` vía `safeUrl()` (`web/src/lib/security/safe-url.ts`).
- El snippet de evidencia **no se interpreta**: se muestra byte a byte.
- Si una vista futura "necesitara" HTML, se para y exige sanitizado concreto
  más veto del `safety-guardian`. El default es no.

## Autoridad y sesión

- La UI **refleja** estados; no los otorga. El scope, el gate y el aborto los
  decide FastAPI. Zod es una pista de UX, no una validación de seguridad.
- CSRF double-submit: el token viaja en `<meta name="csrf-token">` y
  `apiFetch` lo manda en `x-csrf-token` en POST/PUT/PATCH/DELETE
  (`web/src/lib/api/browser.ts`). Bootstrap del token: `GET /api/auth/me`
  (cuerpo 200 / cabecera 401 — ADR-0015).
- **Ocultar un control no sustituye al 403 del servidor.** Un viewer no ve
  controles de mutación **y** el API le responde 403 (T3: gating de Users).
- `GET` de lectura y el SSE no llevan CSRF.

## Cabeceras

- API: `api/security_headers.py` (CSP, frame-ancestors, nosniff, HSTS solo
  HTTPS no-local).
- Documento de Next: `web/next.config.ts`. En producción **sin**
  `unsafe-eval`; `unsafe-inline` solo si el shell lo necesita y documentado.
  La CSP de FastAPI **no** se relaja para "arreglar" Next.
- El proxy no reenvía cabeceras internas ni loguea cookies.

## Paridad y contrato

- CLI y UI leen el mismo `ScanOrchestratorService` y muestran lo mismo para el
  mismo `run_id`.
- Tipos del API: `web/src/lib/api/types.ts` re-exporta
  `lib/api/generated/schema.d.ts` (generado de `/openapi.json`). No duplicar
  enums a mano.
- Estados por página (loading, empty, error, failed, aborted) diferenciados;
  `prefers-reduced-motion` respetado.

## Checklist

- [ ] Sin `dangerouslySetInnerHTML` ni markdown-a-HTML con datos del target.
- [ ] URLs por `safeUrl()`; nada de `javascript:` ni `data:`.
- [ ] Mutaciones con `apiFetch` (CSRF) y manejo explícito de 403.
- [ ] Controles de mutación ocultos a viewers **y** 403 verificado en el API.
- [ ] Sin CDN ni orígenes de terceros; assets empaquetados.
- [ ] Enums del API importados del schema generado, no redefinidos.
- [ ] Download: redaction default `contacts` en UI; el API sigue en `none` si no hay query.
- [ ] Suite `web/`: Vitest verde y `playwright` (wizard + auth) cuando aplique.
