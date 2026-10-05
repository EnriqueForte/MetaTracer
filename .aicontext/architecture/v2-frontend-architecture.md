# Arquitectura de Web V2

Arquitectura aceptada con el ADR-001 (2026-09-26). No es código. Depende de [ADR-001](ADR-001-nextjs-react-migration.md), del [contrato](api-contract-v1.md) y de la [dirección visual](v2-visual-direction.md).

Web V1 (Jinja2, Alpine CSP 3.17.4, Tailwind compilado, `metatracer.css`) no se modifica desde este documento. `.aicontext/ui/*` sigue siendo su contrato.

## Stack, validado

| Pieza | Decisión | Motivo |
| :--- | :--- | :--- |
| Next.js App Router | Aceptado como shell y router, con `basePath: '/v2'` | Layouts, rutas y convivencia con V1. No se usa para mover negocio al servidor |
| React + TypeScript | Aceptado | El hueco real es la falta de módulos tipados |
| Tailwind | Aceptado dentro de `web/` | Aislado del `tailwind.css` precompilado de V1. Versión mayor: pregunta abierta del ADR (3.4 vs 4) |
| shadcn/ui | Aceptado solo como primitivas copiadas al repo | Sin CDN. No sustituye badges de severidad ni el gate de scope |
| Lucide | Aceptado, bundled | Sustituye la ausencia de icon font. Sin CDN |
| TanStack Query | Aceptado para estado de servidor; instalado en TASK-35 (`5.104.1`) | Runs, findings, scopes, stats, users. No para el tick SSE |
| Zod | Aceptado en formularios; instalado en TASK-35 (`4.6.5`) | Advisory. Pydantic manda. Se importa solo desde `src/lib/validation/zod.ts`, que activa `jitless` (sin él Zod prueba `new Function` y la CSP sin `unsafe-eval` registra una violación). Prohibido `zod/compile` |

TanStack Query no usa `dehydrate`, `hydrate` ni `HydrationBoundary`: serializarían en el HTML datos del servidor que incluyen snippets del target. Reabrirlo exige revisión de `safety-guardian`.
| Estado global tipo Redux | Rechazado | No hay un estado de cliente que no quepa en Query + un store pequeño de progreso |
| BFF que reexponga `/api` | Rechazado | Duplicaría auth y sería un segundo lugar donde saltarse el scope |

Si en la fase 3 el runtime de Next exige `unsafe-eval` o un origen de script de terceros para funcionar, se para. No se relaja la CSP de `security_headers.py` para desbloquear el bundle.

## Árbol previsto (no creado)

```
web/
  package.json          # lockfile; lista cerrada
  src/app/              # App Router, basePath /v2
  src/components/ui/    # primitivas shadcn
  src/components/domain/# severity, evidence, scope gate, stages
  src/lib/api/          # cliente fino sobre tipos generados
  src/lib/api/generated/# salida de openapi-typescript; no editar
  src/lib/sse/          # un cliente de ProgressEvent
  src/lib/security/     # safeUrl, render policy
```

`web/` no importa `src/metatracer/`. El proceso Next no abre SQLite ni llama a proveedores LLM.

## Router y componentes

- **Server Components:** layout, nav estática, skip-link, aviso ético (texto fijo en inglés, el mismo que V1). Sin `fetch` al API en el servidor en la versión inicial.
- **Client Components:** cualquier vista que lea `/api` o escuche SSE, y todos los formularios.
- Motivo: la sesión es cookie HttpOnly + CSRF. Un Server Component que reenvíe cookies es un segundo cliente HTTP, fácil de loguear mal y fácil de olvidar en una mutación. Se puede reabrir más adelante con un ADR corto si hace falta SEO o un primer paint con datos. Hoy la herramienta es un operador ya autenticado; el first paint vacío con skeleton es aceptable.

Rutas de paridad (bajo `/v2`):

| Ruta V2 | Equivale a | Notas |
| :--- | :--- | :--- |
| `/v2` | `GET /` | Wizard. Label de nav: Reconnaissance |
| `/v2/runs` | `GET /runs` | History |
| `/v2/runs/[runId]` | `GET /runs/{run_id}` | Progreso, findings, exports |
| `/v2/dashboard` | `GET /dashboard` | |
| `/v2/scopes` | `GET /scopes` | |
| `/v2/users` | `GET /users` | Visible si auth off o rol operator; el API igual rechaza al viewer |
| `/v2/login`, `/register`, `/setup` | shells V1 | Sin nav y sin campana |

No se crean `/targets`, `/settings`, `/ai`, `/reports`.

## Estado

- **Servidor:** TanStack Query. Claves por recurso (`['run', id]`, `['findings', id, filters]`). Al cerrar el SSE se invalidan run, findings y notifications.
- **UI:** estado local del formulario y del drawer.
- **Progreso:** store mínimo (último `ProgressEvent` por `run_id`). No se mete en Query: un tick cada etapa no es un recurso REST.
- Errores de red y 401/403 se distinguen. Un 401 con auth on lleva a `/v2/login`. Un 403 pinta `detail` como texto.

## Formularios

Zod refleja las reglas que el operador puede entender antes del POST:

- targets no vacíos;
- exactamente una fuente de scope;
- `scope_confirmed` solo pasa a `true` en el submit del modal, nunca como default del schema;
- `reasoning_depth` en el enum.

El modal sigue siendo un gate: checkbox desmarcado, foco inicial en cancelar, botón deshabilitado hasta confirmar. Textos V1 a conservar: título `Confirm authorized scope`; 409 “Another scan is already running; wait for it to finish.”; 403 de scope “The scope confirmation was rejected by the server.” Esos textos son de UI (inglés). El `detail` del servidor, si se muestra además, va como texto.

## SSE en el cliente

Un solo módulo. No reimplementa etapas ni decide el status final.

1. Tras el 202, navegar a `/v2/runs/{runId}`.
2. `GET /api/runs/{id}` para el snapshot.
3. `new EventSource('/api/runs/' + encodeURIComponent(runId) + '/stream')`. Same-origin, la cookie viaja sola. Sin polyfill que abra otro host.
4. `onmessage`: `JSON.parse` y validar con el tipo generado (o un Zod estrecho del `ProgressEvent`). Si el JSON no encaja, se ignora el evento y se registra un error de contrato; no se pinta HTML con el cuerpo crudo.
5. Stages de trabajo actualizan el indicador. `completed`: cerrar stream, invalidar queries. `failed` (etapa SSE): cerrar stream, `GET` del run, y recién ahí mostrar `aborted` o `failed` según `status`.
6. `onerror`: cerrar y polling cada 2 s del GET hasta `completed` | `failed` | `aborted`, igual que `run.html`.
7. Keep-alive: ninguna acción.
8. Reconexión: volver a abrir `EventSource`. El replay del servidor hace innecesario un cursor de cliente. Aplicar eventos de forma idempotente.
9. Desmontaje de la página: `close()` del EventSource. Eso no cancela el scan.

`current_asset` y `message` son texto. Pueden contener URLs o rutas del objetivo.

## Información: existe vs futuro

**Existe y entra en paridad** (datos reales, sin métricas inventadas):

- Dashboard: solo campos que `dashboard.html` ya muestra de `GET /api/stats`.
- Reconnaissance: wizard.
- Scan progress: siete etapas + terminal.
- Findings, severity, confidence, evidence, field source, asset.
- Security analysis en el sentido de producto actual: severidad heurística/agente, justificación, impacto, remediación, pasos de reproducción, feedback. No un módulo nuevo de “threat intel”.
- AI analysis: los campos de prosa del `FindingResponse` y `agent_usage` del dashboard. Separados visualmente de `evidence_snippet`, como pide la IA de V1.
- Reports: cinco descargas en la página del run.
- History, scopes, notifications, configuration solo en lo que ya hay (reasoning depth, usuarios, invitaciones). No hay página Settings.

**Futuro, fuera de paridad:** UI de knowledge, UI de webhooks, UI de watch, breadcrumbs si se quieren (V1 los documenta y no los tiene; no son regresión si faltan; sí lo son si se prometen como paridad — la matriz los marca como “documentado, no implementado”), páginas Targets / Settings / AI / Reports.

## Política cybersecurity del frontend

Módulo `safeUrl(value) -> string | null`:

- Acepta únicamente URLs `http:` y `https:` parseadas.
- Rechaza `javascript:`, `data:`, protocol-relative raras, y cualquier cosa que no parsee.
- El href usa el resultado o no hay enlace. El texto de la URL hostil sí se muestra, como texto, para que el operador vea qué llegó.

Render:

- React text nodes / equivalentes de `x-text` para snippet, título, prosa, errores, nombres, targets, dominios.
- Listas de `reproduction_steps` como `<li>` de texto, no como HTML.
- Prohibido en CI: `dangerouslySetInnerHTML`, `innerHTML`, `insertAdjacentHTML`, `document.write`, markdown-it / rehype sin un ADR específico.
- El contenido del modelo no se inyecta en un system prompt del navegador. Web V2 no llama al LLM.

Secretos:

- Ninguna clave en `NEXT_PUBLIC_`.
- El token de setup lo teclea el operador en el formulario, igual que V1; no se hornea en el bundle.
- No loguear cuerpos de login ni cookies.

Supply chain:

- Dependencias fijadas, lockfile, sin `latest`, sin CDN, sin postinstall opacos si se pueden evitar.
- La imagen Docker de Python no gana Node en este ADR.
- `safety-guardian` revisa el diff de `package.json` / lockfile como perímetro, igual que hoy revisa `pyproject.toml`.

Cabeceras del documento Next (fase 3, a concretar con el bundle real): `frame-ancestors 'none'`, `base-uri 'self'`, `object-src 'none'`, `connect-src 'self'`, sin orígenes de script de terceros. `form-action` solo al propio origen.

## Agentes

No se crean archivos en `.cursor/agents/` en esta fase. La propuesta es la mínima que no rompe el veto único ni reescribe agentes V1.

### Se quedan como están (V1 o backend)

| Agente | Por qué no se toca |
| :--- | :--- |
| `ui-engineer` | Contrato explícito: Jinja, Alpine, sin React, sin Node. Sigue siendo el dueño de `templates/` y `static/` |
| `ui-architect` | `readonly`, diseño sobre el stack V1, y prohíbe proponer esta migración dentro de un rediseño Jinja. Sigue dueño de `.aicontext/ui/` |
| `pipeline-engineer` | Núcleo determinista. Web V2 no le pide cambios |
| `llm-agent-engineer` | Grafo, prompts, guard. El cliente solo muestra su salida |
| `test-engineer` | pytest, fixtures, mock origin, Docker Python, cero red real. Sigue cerrando que V1 no se rompe |
| `docs-architect` | Coherencia de `.aicontext` al cerrar fases. No existe `docs-agent-engineer` y no hace falta crearlo |
| `safety-guardian` | Único veto de merge. Se le pedirá, cuando exista `web/`, ampliar el checklist (XSS DOM, env pública, lockfile, CSP de Next, cookies a través del proxy). No se crea un segundo agente de seguridad: partir el veto lo debilita |

### Se proponen, todavía sin archivo

| Agente | Hace | No hace |
| :--- | :--- | :--- |
| `v2-architect` | Orquesta el programa: analiza, parte fases, paraleliza lo independiente, detecta choques, pide revisión, ejecuta checkpoints, **para** ante riesgo de arquitectura o de contrato | No implementa React. No edita agentes V1. No puede anular al `safety-guardian`. No “aprovecha” para cambiar el pipeline |
| `react-engineer` | Código solo bajo `web/`. Sigue la política de render y el contrato generado | No edita `src/metatracer/`. Si cree que el API está mal, para y escala. No añade dependencias fuera de la lista aceptada |
| `frontend-test-engineer` | Vitest, Testing Library, Playwright. Cero Internet. No mockea el safety core del servidor: los tests de integración hablan con el API real o con el mock origin ya existente | No relaja pytest. No cambia producto para poner verde un test de UI |

### Se evaluaron y no se crean

| Candidato | Motivo |
| :--- | :--- |
| `frontend-architect` | Solapa a `v2-architect` y choca de nombre con `ui-architect` |
| `frontend-security-engineer` | El veto tiene que seguir siendo uno |
| `api-contract-engineer` | La fase 2 es un encargo del orquestador (generar tipos, anotar huecos). Se promueve a agente solo si la generación pasa a ser trabajo recurrente |
| `migration-engineer` | El corte es un checkpoint de proxy, no un rol permanente |

### Cómo orquesta `v2-architect`

1. Lee el contrato y la matriz antes de encargar una pantalla.
2. Paraleliza solo lo que no comparte contrato ni política de seguridad (p. ej. dashboard y historial, después de existir el cliente API).
3. No paraleliza el wizard de scope con un cambio de `ScanRequest`.
4. Si una tarea pide tocar FastAPI, para. Entran `pipeline-engineer` (si es dominio) y siempre `safety-guardian` antes de merge.
5. Al cerrar fase: tests de esa fase, contrato sin diff inesperado, V1 (pytest de páginas y API) en verde, nota corta de `docs-architect` si el código ya existe.
6. Stoppers del ADR: breaking change, función perdida, bypass, dependencia nueva no listada, negocio duplicado en el cliente.

Solape conocido y aceptado: `test-engineer` y `frontend-test-engineer` comparten el mock origin y la regla de cero red real. No comparten el permiso de editar el otro árbol.

## Testing (diseño)

Backend, sin cambio de mandato: pytest, marca `e2e` aparte, cobertura 85 % en los cuatro paquetes que ya exige CI.

Frontend:

- Vitest + Testing Library: `safeUrl` (javascript:, data:, http, vacío), snippet con `<script>` renderizado como texto, checkbox de scope desmarcado y botón disabled, 403/409 pintados como texto, lista vacía de findings distinta de error de carga, `severity: null` sin badge inventado.
- Playwright: flujo wizard → 202 → página de run contra Uvicorn de test y el mock origin del repo (`tests/fixtures/mock_origin.py`), con `METATRACER_ALLOW_LOOPBACK` solo en el proceso de test, igual que el e2e actual. Auth on y auth off. Viewer no completa un POST. SSE: al menos un evento de etapa y un terminal, o el fallback de polling si se corta el stream.
- Hostil: metadata y prosa con HTML y URLs `javascript:` en la respuesta del API de test (fixture), comprobando que el DOM no crea un nodo script ni un href peligroso.
- No forman parte de la paridad y no se testean como features: knowledge UI, webhooks UI, watch UI.

CI: job nuevo. El job `pr` de Python no instala Node hasta que el guardian acepte el perímetro. Mientras, Web V2 puede vivir en un workflow separado que no bloquee el merge de `src/` si el path `web/` no cambió — el detalle del workflow es de la fase 12, no de hoy.
