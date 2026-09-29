# ADR-001: Migración del frontend a Next.js / React (Web V2)

**Fecha:** 2026-09-26
**Estado:** Aceptada (2026-09-26). Autoriza el programa Web V2. No autoriza todavía `package.json` ni cambios en `src/metatracer/`.
**Ámbito:** capa Web. No es un ADR de pipeline, detectores, agentes LLM ni base de datos.
**Relacionado:** [contrato API](api-contract-v1.md) · [arquitectura frontend](v2-frontend-architecture.md) · [dirección visual](v2-visual-direction.md) · [plan de migración](../migrations/v1-to-v2-frontend.md) · [matriz de paridad](../migrations/feature-parity-matrix.md)

## Context

MetaTracer (paquete `0.6.0`) es una plataforma de descubrimiento de metadata sensible para bug bounty y red team autorizados. El núcleo ya está cerrado: safety core, ingestión, cinco detectores, clasificador heurístico, grafo LangGraph, reportes, CLI Typer y una Web UI Jinja2.

La Web UI actual no es un prototipo. TASK-26 (aplicada 2026-09-21) fijó un design system propio (`static/metatracer.css`, tokens `.mt-*`), Tailwind 3.4.16 compilado offline y Alpine CSP 3.17.4 vendorizado. Diez plantillas en `src/metatracer/api/templates/` consumen la API JSON. La lógica de pantalla vive en scripts inline (`Alpine.data`). No hay bundler ni React.

En paralelo, la API creció más que las páginas. `create_app` en `src/metatracer/api/app.py` expone del orden de 39 rutas JSON (runs, scopes, stats, notifications, feedback, knowledge, auth, users, invitations, webhooks) más nueve páginas HTML. Knowledge, webhooks y el modo `watch` tienen backend y CLI, y no tienen página.

Hay una colisión de nombres que este ADR fija:

| Nombre en el repo | Qué es |
| :--- | :--- |
| Plataforma v1.0–v1.2, v2.0–v2.4, v3.0–v3.1 | Slices Python ya construidos (scopes, dashboard, RAG, webhooks, watch, Postgres, auth). El paquete es `0.6.0`. |
| **Web V1** | La UI Jinja2 + Alpine que sirve FastAPI hoy. |
| **Web V2** | El programa de este ADR: una aplicación Next.js que consume el mismo FastAPI. |

“MetaTracer AI V2” en esta decisión significa **Web V2**. No reabre la plataforma v2.0 ni sustituye el paquete Python.

Los agentes `ui-architect` y `ui-engineer` prohíben proponer React “para conseguir una UI más moderna” y obligan a rediseñar sobre Jinja. Esa prohibición sigue vigente **para Web V1**. Este ADR no la reescribe. Abre un carril nuevo, con agentes nuevos, sin convertir a esos dos agentes en agentes React.

## Problem

El problema no es estético. TASK-26 ya resolvió la estética sobre el stack actual.

El problema es de arquitectura de aplicación:

1. **La UI y la API ya no crecen al mismo ritmo.** Cada flujo nuevo (auth, invitaciones, filtros, drawer, feedback) añade otro `Alpine.data` inline. No hay módulos, no hay tipos y no hay tests de componente: la red de seguridad es pytest de integración contra HTML.
2. **El contrato con el navegador es implícito.** FastAPI genera `/openapi.json` por defecto (no hay `docs_url=None` en `app.py`), pero nadie genera un cliente. La UI y los modelos Pydantic pueden divergir sin que el compilador lo vea.
3. **La política de renderizado está repetida en cada plantilla.** Hoy se cumple (`x-text`, `safeUrl()` en `run.html`, cero `|safe` / `x-html` / `innerHTML`). Mantenerla al añadir superficies (knowledge, webhooks) depende de revisión humana en cada archivo HTML.
4. **Varias capacidades de plataforma no tienen UI** (`/api/knowledge/*`, `/api/webhooks/*`, `metatracer watch`). Construirlas como más plantillas alarga el patrón que ya está en el techo. Construirlas en Web V2 antes de la paridad las convertiría en features nuevas disfrazadas de migración. Quedan fuera hasta cerrar la paridad.

Una migración “porque React es moderno” no resuelve nada de esto y tira el trabajo de TASK-26. Por eso la decisión de abajo es condicional.

## Goals

- Dejar Web V1 funcional y desplegable durante todo el programa.
- Añadir Web V2 como cliente del FastAPI existente, sin convertir al navegador en autoridad de seguridad.
- Congelar el contrato HTTP/SSE y tiparlo desde OpenAPI, no reescribiéndolo a mano.
- Poder comparar V1 y V2 en el mismo origen, hacer rollback quitando una ruta de proxy y no tocar SQLite ni el pipeline.
- Centralizar el renderizado de datos hostiles (snippets, URLs, prosa del modelo, nombres de fichero) en una política comprobable.
- Preparar el crecimiento posterior (knowledge, webhooks, watch) **después** de la paridad, no dentro de ella.

## Non-goals

No se migran, y este ADR no autoriza cambiarlos:

- `ScanOrchestratorService`, pipeline, extractors, detectors, clasificador, agentes LLM, reportes, SQLite/Postgres, CLI.
- Contratos de seguridad: `scope_confirmed`, `ScopeValidator`, `NetworkSafetyGuard`, `safe_httpx_request`, redirects in-scope, `METATRACER_ALLOW_LOOPBACK`.
- Reglas `.cursor/rules/`, skills de safety/contracts/supply-chain, ni los agentes V1 (`ui-engineer`, `ui-architect`).
- Sustituir FastAPI, Uvicorn o el design system `.mt-*` como lenguaje visual de dominio.
- Inventar páginas que el mapa de información ya marca como inexistentes: Targets, Settings, AI y Reports como rutas propias (`.aicontext/ui/ui-architecture.md` §3).
- Añadir cancelación de scan, CORS nuevo, o un BFF que reimplemente la API.
- Un big-bang que apague `/` de FastAPI el mismo día que exista el primer componente React.

## Current Architecture

```
Operador
   │
   ├── CLI Typer ──────────────┐
   │                           ▼
   └── Navegador                ScanOrchestratorService
         │                      (única autoridad de scan)
         │  mismo origen
         ▼
      FastAPI
         ├── HTML Jinja2 + Alpine  (Web V1, páginas en pages.py)
         ├── JSON /api/*           (contratos Pydantic)
         └── SSE  GET /api/runs/{run_id}/stream
                   ProgressBus (memoria de proceso, replay)
```

Hechos verificados en código, no en la documentación antigua:

- **Autoridad.** El orquestador rechaza `scope_confirmed=false` antes de crear el run (`_begin_scan`). La UI solo puede enviar `true` después del modal; el servidor sigue siendo quien decide. Un asset fallido no tumba el run; una `SecurityViolationError` o `ScopeNotConfirmedError` persiste `run.status=aborted`.
- **SSE.** `ProgressEvent` (`run_id`, `stage`, `current_step`, `total_steps`, `message`, `current_asset`) lo emite el orquestador y lo reparte `ProgressBus`. Etapas de trabajo: `scope_validation`, `discovery`, `downloading`, `extraction`, `detection`, `ai_analysis`, `report_generation` (`TOTAL_STEPS = 7`). Terminales SSE: `completed` y `failed`. El aborto de safety **no** es una etapa SSE: `_fail` emite `stage=failed` y persiste `status=aborted`. El cliente distingue leyendo `GET /api/runs/{id}`.
- **Reconexión.** `subscribe()` reinyecta el historial. Keep-alive cada 15 s (`: keep-alive`). `run.html` ante `onerror` cierra `EventSource` y hace polling cada 2 s hasta `completed` | `failed` | `aborted`. No existe endpoint de cancelación.
- **Sesión.** Cookie `metatracer_session` (HttpOnly, `SameSite=Lax`, `Path=/`). CSRF double-submit: cookie `csrf_token` legible y header `x-csrf-token`. No hay `CORSMiddleware`. CSP: `connect-src 'self'`. Auth es opcional (`METATRACER_AUTH_ENABLED`).
- **Renderizado.** Jinja autoescape. Las plantillas no usan `|safe`, `x-html` ni `innerHTML`. `safeUrl()` en `run.html` solo admite `http:` y `https:`.
- **OpenAPI.** Schema por defecto de FastAPI (`/openapi.json`, `/docs`, `/redoc`). Las páginas HTML van con `include_in_schema=False`. Varias rutas de webhooks declaran `dict`, no un modelo nombrado.

### Discrepancias documentación ↔ código

No se corrigen en esta fase. Web V2 debe seguir el código.

| Fuente | Dice | Código |
| :--- | :--- | :--- |
| `src/metatracer/api/app.py` (docstring inicial) | No hay autenticación; solo el bind | Auth opcional TASK-24/25 en el mismo factory |
| `.aicontext/tasks/06-interfaces.md` | Sin auth, Tailwind CDN, export `md`/`json`, un scan | Auth opcional, Tailwind compilado, cinco formatos, `METATRACER_MAX_CONCURRENT_RUNS` |
| `.aicontext/ui/ui-architecture.md` §1 | Nav horizontal; `_fail` persiste el aborto como `failed`; bugs `manual-scope` y KPI “Scope domains” | `base.html` es sidebar; `_fail` persiste `aborted` y el SSE usa `failed`; el inventario de plantillas de esta fase no encontró esos dos bugs de markup |
| `.aicontext/ui/ui-architecture.md` §4 | Breadcrumb en el run | `run.html` no tiene breadcrumb |
| `static/metatracer.css` y `component-map.md` | Comentarios de CDN | Runtime local, sin CDN |
| `.aicontext/tasks/README.md` tabla de enums | No lista `skip_reason` | `SkipReason` existe en `db/models.py` y en `.cursor/rules/data-contracts.mdc` |
| `services/notifications.py` docstring | `kind` es `completed` \| `failed` | `_notify_run_finished` publica `kind=status`, y el aborto llega como `aborted` |
| `docker-compose.yml` | imagen `metatracer:0.5.1` | `pyproject.toml` versión `0.6.0` |
| `.cursor/agents/` | El encargo menciona `docs-agent-engineer` | No existe. El rol de documentación es `docs-architect` |
| Enum `detector_method` | `rule` \| `heuristic` \| `agent` | La detección persiste `rule`. No hay asignación de `agent` en `src/metatracer/` |

## Proposed Architecture

```
Navegador  (un solo origen: scheme + host + puerto)
   │
   │   /v2/*     aplicación Next.js (basePath), estática de UI
   │   / y HTML  FastAPI Web V1, intacta
   │   /api/*    FastAPI, incluida el SSE
   │   /static/* assets V1
   ▼
Reverse proxy (prod) o rewrite de Next solo en dev
   │
   ├── proceso Next (web/)     sin secretos de scan, sin LLM, sin scope
   └── proceso Uvicorn         autoridad: orquestador, safety, DB
```

Decisiones de encaje:

1. **Mismo origen.** Cookies `SameSite=Lax` y `connect-src 'self'` impiden un frontend en otro puerto u otro host sin abrir CORS y sin debilitar la sesión. No se añade CORS. No se amplía `Domain` de la cookie.
2. **`basePath: '/v2'`** durante la coexistencia. Las llamadas de datos son absolutas a `/api/...`, no bajo `/v2/api`.
3. **Next no es BFF de negocio.** No reimplementa runs, scope ni safety. Los Server Components pintan el shell. Los datos autenticados y las mutaciones viven en Client Components (TanStack Query + `fetch` same-origin con `credentials: 'same-origin'` y header CSRF). Así no aparece un segundo sitio donde olvidar el reenvío de la cookie.
4. **SSE no termina en Next.** `EventSource('/api/runs/{id}/stream')` habla con FastAPI a través del proxy, con buffering desactivado. El header `X-Accel-Buffering: no` ya lo pone `stream_run`.
5. **Paquete aislado `web/`.** `package.json` no entra en `pyproject.toml`. La imagen Python no gana Node. El perímetro de supply chain es nuevo y lo revisa `safety-guardian` antes del primer install.
6. **Tipos generados** desde `/openapi.json` (`openapi-typescript` o equivalente fijado en la fase 2). Zod solo en fronteras de formulario, como pista de UX. Pydantic sigue siendo la autoridad.
7. **Política de renderizado única:** nodos de texto. Prohibido `dangerouslySetInnerHTML` y cualquier markdown-a-HTML. URLs solo `http`/`https` (`safeUrl`). Snippets, títulos, prosa del modelo y nombres de fichero son datos hostiles.
8. **shadcn/ui + Lucide** como primitivas (dialog, table, sheet), compiladas en el bundle, sin CDN. Los componentes de dominio (severity, evidence, scope gate, etapas) siguen los tokens `.mt-*`, portados como variables CSS. shadcn no redefine la semántica de severidad.

Detalle de módulos, SSE en cliente, IA y agentes: [v2-frontend-architecture.md](v2-frontend-architecture.md).

## Alternatives Considered

| Alternativa | Por qué no |
| :--- | :--- |
| Seguir solo en Jinja/Alpine | Válida para el estado actual y es el fallback si este ADR se rechaza. No da tipos ni tests de componente, y cada superficie nueva repite la política de XSS en HTML. Se conserva como Web V1, no se descarta el producto. |
| Reescribir V1 in situ (sustituir plantillas por React dentro de FastAPI) | Rompe el rollback y mezcla dos toolchains en el paquete Python. Contradice “V1 permanece funcional”. |
| SPA Vite sin Next | Menos superficie de servidor, pero el encargo pide App Router, layouts y una base que pueda crecer. El uso real previsto es mayoritariamente cliente; Next se acepta como router y shell, no como lugar donde mover negocio. Si la fase 3 demuestra que App Router obliga a relajar CSP por `unsafe-eval` o a un BFF, se para y se reevalúa Vite. |
| Next en otro origen + CORS con credenciales | Amplía la superficie (origen permitido, cookies cross-site). Incompatible con el modelo actual sin un rediseño de auth que este ADR prohíbe. |
| Tipos TypeScript escritos a mano | Duplican Pydantic y se desactualizan. Solo se escriben a mano los huecos que OpenAPI no exprese, y cada hueco es un hallazgo de fase 2, no un estilo. |
| Migrar también el pipeline “ya que estamos” | No hay evidencia de que Web V2 lo necesite. Cualquier cambio de contrato para “ayudar al frontend” es un stopper. |

## Decision

**Se acepta Web V2 como programa paralelo y condicionado. No se acepta un rewrite.**

La migración está justificada por techo de arquitectura, contrato tipado y política de renderizado testeable. No está justificada por apariencia. Si el único objetivo fuera visual, la decisión sería **no migrar** y cerrar aquí: TASK-26 ya entregó ese rediseño.

Condiciones que bloquean la fase 3 (el primer `package.json`):

1. Checkpoint humano que marque este ADR como aceptado. **Cumplida el 2026-09-26.**
2. Topología de un solo origen, sin CORS nuevo, documentada en el proxy de desarrollo.
3. Lista cerrada de dependencias npm revisada por `safety-guardian` **antes** de instalar.
4. Spike de generación de tipos contra el `/openapi.json` real. Si hace falta cambiar modelos Python para que el schema sea generable, se para y se trata como cambio de contrato, no como detalle de frontend.
5. La suite pytest de V1 sigue en verde. La fase de fundación no modifica `src/metatracer/`.

Ningún cambio de backend es necesario para soportar Web V2 si el proxy same-origin vive fuera del proceso Python. Esa es la conclusión del descubrimiento: pipeline, detectores, extractores, SQLite, CLI y safety permanecen quietos.

## Consequences

- Aparece un segundo frontend que hay que mantener hasta un ADR de corte (no es este).
- Aparece un perímetro Node (lockfile, CI, imagen o stage aparte).
- `.aicontext/ui/*` sigue siendo el contrato de Web V1 para `ui-engineer`. No se reinterpreta como especificación React.
- Los agentes V1 no se reescriben. La gobernanza nueva está propuesta en la arquitectura frontend y **no se materializa** hasta el checkpoint.
- `ui-architect` sigue pudiendo vetar, en su carril, un rediseño Jinja que cuele React. Web V2 no usa ese agente.

## Benefits

- Paridad trazable (matriz) y rollback por configuración de proxy.
- El cliente deja de adivinar enums, códigos y la diferencia `aborted` / `failed`.
- Los tests de snippet hostil, URL y gate de scope pueden vivir junto al componente, además del pytest que ya protege el servidor.
- Las capacidades sin UI (knowledge, webhooks, watch) tienen un sitio futuro que no es otra plantilla de 400 líneas. No entran en este programa.

## Risks

| Riesgo | Severidad | Contención |
| :--- | :--- | :--- |
| XSS por `dangerouslySetInnerHTML` o un renderer markdown | Alta | Lint que falle el build; política de texto; revisión del `safety-guardian` en cada PR de `web/` |
| Next se convierte en autoridad (scope “validado” en cliente, targets reescritos) | Alta | Zod es advisory. El POST sigue siendo el `ScanRequest` del servidor. El checkbox nace desmarcado |
| CORS o segundo origen “temporal” en dev | Alta | Prohibido. Dev también pasa por rewrite/proxy al mismo origen que ve el navegador |
| SSE buffereado por el proxy o por un route handler de Next | Alta | El stream no se implementa en Next. Buffering off. Test de integración que recibe un evento antes del terminal |
| Supply chain npm (typosquat, postinstall) | Alta | Lista cerrada, lockfile, sin CDN, imagen Python intacta, veto del guardian antes del install |
| CSP más débil que la actual (`unsafe-eval`, terceros) | Alta | La CSP de FastAPI no se relaja para “arreglar” Next. Si el bundle de Next no cabe en una CSP sin `unsafe-eval`, stopper |
| Dos UIs divergentes | Media | Matriz de paridad. V1 no se borra. Corte solo con ADR posterior |
| Confundir Web V2 con la plataforma v2.0 ya shipped | Media | Tabla de nombres de este ADR |
| Filtrar secretos con `NEXT_PUBLIC_*` | Alta | Prohibido poner claves LLM, sesión o tokens de setup en env pública. Next no necesita la clave del modelo |
| Pérdida silenciosa de una pantalla V1 | Alta | Matriz. Checkpoint de paridad antes de cualquier corte |

## Security Impact

La autoridad permanece en FastAPI: confirmación de scope, validación de target, gates, abortos y excepciones de red. El frontend refleja estados; no los otorga.

Datos no confiables, siempre como texto:

- metadata y `evidence_snippet` (el objetivo puede ser hostil);
- `severity_justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps`, `title` (salida de LLM, también hostil; un modelo puede intentar inyección de prompt reflejada como HTML);
- `source_url`, `asset_final_url`, nombres de fichero, `error_message`.

No se introducen equivalentes de `|safe`, `x-html` o `dangerouslySetInnerHTML`. Si alguna vista futura creyera necesitarlos, se para y exige sanitizado concreto más veto del `safety-guardian`. El default es no.

Auth, CSRF y cookies no se reimplementan. Web V2 lee la cookie CSRF y manda `x-csrf-token` en POST/PUT/PATCH/DELETE, igual que `MetaTracerUI.authFetch`. Los GET de lectura, incluido el SSE, no llevan CSRF (el servidor no lo exige). Un viewer no ve controles de mutación; ocultarlos no sustituye al 403 del servidor.

Cabeceras: las de API las sigue poniendo `security_headers.py`. Las de los documentos HTML de Next son un trabajo de la fase 3 y no pueden ser más permisivas que la CSP actual en `script-src` de terceros. `'unsafe-inline'` existe hoy por los scripts de plantilla; Web V2 debe intentar eliminarlo en **su** documento, no copiarlo por inercia. Si no puede, se documenta el motivo y lo revisa el guardian. No se añade `unsafe-eval`.

El proxy no debe reenviar al navegador cabeceras internas ni loguear `metatracer_session`.

## Operational Impact

- Dos procesos en desarrollo: Uvicorn (V1 + API) y Next (solo UI). Un proxy los presenta como un origen.
- Producción, hasta el corte: el servicio actual no cambia. `/v2` es opt-in.
- Docker: la imagen `python:3.12-slim` actual no instala Node. Un servicio compose aparte, si hace falta, entra en la fase 3 con revisión de supply chain. La discrepancia de tag `0.5.1` vs `0.6.0` es previa; no se “arregla” dentro de este programa.
- Rollback operativo: quitar la ruta `/v2` del proxy y borrar o ignorar `web/`. No hay migración de datos.

## Testing Impact

- pytest sigue siendo la red del backend y de Web V1. No se relajan asserts ni se mockea `ScopeValidator` / `NetworkSafetyGuard` en integración.
- Web V2 añade Vitest + Testing Library (política de render, gate de scope, estados vacíos y de error) y Playwright contra el API real con el mock origin ya existente. Cero Internet real.
- El job de cobertura Python (`metatracer.core`, `detectors`, `extractors`, `reports`, 85 %) no absorbe el frontend. Job aparte.
- Detalle en el plan de migración y en la arquitectura frontend.

## Migration Strategy

Resumen. El plan ejecutable es [v1-to-v2-frontend.md](../migrations/v1-to-v2-frontend.md).

0. Descubrimiento (este conjunto de documentos).
1. Aceptación de este ADR.
2. Contrato y generación de tipos, sin UI.
3. Fundación `web/` tras el veto de dependencias.
4. Tokens y primitivas.
5. Shell (nav real, no páginas conceptuales).
6. Wizard de scan y modal de scope.
7. SSE y polling.
8. Findings, evidencia, drawer, feedback.
9. Campos de análisis del modelo (en el drawer, no una página AI).
10. Descargas de reporte.
11. Dashboard, historial, scopes, auth, usuarios, notificaciones.
12. Tests.
13. Revisión de seguridad.
14. Validación de paridad.
15. Coexistencia prolongada. El corte de `/` es otro ADR.

Cada fase para si aparece breaking change, pérdida de función, cambio de contrato, bypass, dependencia no listada o lógica de negocio duplicada en el cliente.

## Rollback Strategy

- **Antes del corte:** Web V1 es el default. Rollback = no enrutar `/v2`. Cero impacto en CLI, DB y API.
- **Después de un corte futuro:** el proxy devuelve `/` a FastAPI. Las plantillas no se habrán borrado en el mismo cambio que encienda Next. Borrar plantillas exige un ADR distinto con la matriz en `migrated`.
- No hay feature flag dentro del orquestador. El flag es la ruta del proxy.
- Un fallo de Web V2 (build, CSP, SSE) no aborta scans: el scan lo sigue pudiendo lanzar la CLI y Web V1.

## Open Questions

1. ¿Se acepta el perímetro npm, sabiendo que la lista cerrada de TASK-00 era solo Python?
2. Tailwind 3.4 (paridad con V1) o Tailwind 4 (lo que pida el CLI actual de shadcn). **Cerrada en la fase 4:** Tailwind **4.3.3** solo en `web/`. V1 permanece en 3.4.16 compilado.
3. ¿El spike de OpenAPI exige `response_model` en webhooks (`dict` hoy)? **Respondida en la fase 2:** el schema se genera sin tocar Python. Las respuestas de webhooks, auth, el dashboard anidado y el SSE quedan abiertas. Cerrarlas es un cambio de contrato aparte. La paridad de scan no lo necesita. Ver [phase-2-contract-spike.md](phase-2-contract-spike.md).
4. ¿Hace falta un route handler de Next para el login, o el `Set-Cookie` de FastAPI atraviesa el rewrite de desarrollo sin perder `Secure` / `Path`? Se prueba en la fase 3 con auth activado. Si el rewrite se come la cookie, se usa proxy externo también en dev y no se “arregla” relajando cookies.
5. ¿Cuánto tiempo conviven `/` y `/v2`? Propuesta: como mínimo hasta paridad + una revisión del guardian. El calendario no es este ADR.
6. ¿Se materializan ya los agentes `v2-architect`, `react-engineer` y `frontend-test-engineer`? Propuesta en la arquitectura; no se crean archivos de agente en esta fase.

## Addendum — dirección visual (2026-09-26)

La aceptación incluye el mapa visual descrito en [v2-visual-direction.md](v2-visual-direction.md), tomado de la estructura de trabajo de la demo BugTrace (barra de comando, canvas, barras de severidad, fila expandible) y no de su catálogo de herramientas.

No añade páginas, enums, CVSS, grafo de ataque, chat ni consola de payloads. `.aicontext/ui/*` sigue siendo el contrato de Web V1.

## Qué autoriza y qué no

Autoriza seguir a la fase 2 (contrato ejecutable, sin UI). Sigue sin autorizar `package.json`, edición de plantillas, edición de agentes ni cambios en `src/metatracer/`, hasta cumplir las condiciones 2 a 5 de la decisión.
