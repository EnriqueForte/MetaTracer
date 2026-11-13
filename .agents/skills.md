# Skills de los agentes desarrolladores — MetaTracer

**Proyecto:** MetaTracer — AI-powered sensitive metadata discovery for Bug Bounty & Red Team
**PRD:** [índice](../.aicontext/PRD.md) · **Backlog:** [tasks](../.aicontext/tasks/README.md)
**Documento hermano:** [agents.md](agents.md) (define los agentes; este define sus skills)
**Versión:** 1.4
**Fecha:** 5 de noviembre de 2026

> **Este archivo es especificación de diseño, no un skill cargable.** Se llama `skills.md` (y no
> `skills/SKILL.md`) a propósito: `.agents/skills/` es una raíz de skills que Cursor recorre, así
> que un `SKILL.md` ahí dentro se registraría como skill real. Los skills funcionales viven en
> `.cursor/skills/<nombre>/SKILL.md`.

---

## 1. Qué es una skill en este proyecto

Una skill es conocimiento de dominio empaquetado que el agente carga **just-in-time**: solo
cuando trabaja en el módulo correspondiente. A diferencia de las rules (`.cursor/rules/`,
siempre activas, lo inviolable), las skills contienen el detalle denso que saturaría el
contexto si estuviera siempre presente.

- **Ubicación real de cada skill:** `.cursor/skills/<nombre>/SKILL.md` (este documento es la
  especificación de diseño; los skills funcionales viven allí).
- **Formato:** frontmatter YAML (`name`, `description` con QUÉ hace y CUÁNDO usarla) + cuerpo
  conciso con progressive disclosure.
- **Regla de oro de autoría:** referenciar los documentos fuente (`.aicontext/tasks/...`) en
  lugar de duplicarlos. Cuando el PRD evolucione, solo hay un sitio que actualizar.
- **Regla de adopción:** crear cada skill de módulo **nuevo** al abrir su slice, no antes.
  Las skills 1–14 existen (incluye `metatracer-onnx`).

### 1.1 Qué capa se lleva cada conocimiento

Con cuatro capas de configuración (rules, skills, prompts de agente y `.aicontext/`) el riesgo
real es **duplicar** y que las copias se desincronicen. Regla de asignación:

| Tipo de conocimiento | Capa | Ejemplo |
| :--- | :--- | :--- |
| Invariante que nunca puede romperse | Rule (`.cursor/rules/`) | "Toda petición HTTP pasa por el wrapper" |
| Contrato compartido entre módulos | Rule | Enums en minúsculas, `severity` NULL hasta clasificar |
| Valor exacto, regex, umbral o trampa de **un módulo** | Skill | Rangos IP bloqueados, techos de severidad, timeouts |
| Rol, procedimiento, límites y criterio de éxito de **quien** trabaja | Prompt del agente (`.cursor/agents/`) | "Cuando te invocan, lee la task y cita su DoD" |
| Especificación de producto y su justificación | `.aicontext/` | Por qué SQLite ahora y Postgres después |

Consecuencia práctica: una skill **no repite** la rule (la referencia), y **no explica cómo
comportarse** (eso es del prompt del agente). Si un párrafo de una skill sirve para cualquier
proyecto Python, no pertenece a la skill.

---

## 2. Catálogo de skills

### 2.1 `metatracer-safety-rules` — Transversal · Prioridad crítica · **Creado**

**Ubicación:** `.cursor/skills/metatracer-safety-rules/SKILL.md`

**Se activa cuando:** se escribe o modifica código de red/HTTP, redirects, validación de
scope, rate limiting o configuración de seguridad.

**Conocimiento que encapsula:**

- `ScopeValidator`: normalización de host (sin esquema/path/puerto, lowercase), matching
  exacto o `endswith("." + domain)`, wildcard `*.dominio` sin apex, `evil-target.com` nunca
  matchea `target.com`, sin Public Suffix List en MVP.
- `NetworkSafetyGuard` (anti-SSRF): resolución DNS de todas las IPs (A y AAAA) y bloqueo de
  loopback, unspecified, RFC 1918, link-local (incluye `169.254.169.254`), CGNAT, ULA IPv6 y
  multicast; `SecurityViolationError` antes de abrir el socket; guard llamada inmediatamente
  antes de cada request (TOCTOU aceptado).
- Wrapper HTTP único `safe_httpx_request`: redirects manuales (máx. 5 hops, re-validados),
  timeouts (10/20/10 s), HEAD con fallback a GET streamed, `DomainRateLimiter` (2 rps) +
  semáforo global.
- Confirmación de scope: `ScopeNotConfirmedError` si `scope_confirmed=False`; scope nunca
  inferido; `METATRACER_ALLOW_LOOPBACK` solo para tests.
- **Logging seguro** (amenaza 13): nunca interpolar crudo un valor del target en un mensaje de
  log; sustituir `\r`/`\n` y truncar a ~150 chars; contexto como campo estructurado. TASK-00
  (0.4.2) fija el formato; esta skill fija qué entra en el mensaje.
- Checklist de revisión de 6 puntos para PRs.

**Amenazas que cubre** ([§4.2 de agents.md](agents.md#42-modelo-de-amenazas-que-todo-agente-lleva-encima)): 1, 2, 3, 13.

**Lo usan:** `safety-guardian` (núcleo de su revisión), `pipeline-engineer`, `test-engineer`.

**Fuente:** `.aicontext/tasks/00-architecture-and-safety.md` (0.3, 0.4.2),
`01-metadata-extraction.md` (1.2).

---

### 2.2 `metatracer-data-contracts` — Transversal · Prioridad crítica · **Creado**

**Ubicación:** `.cursor/skills/metatracer-data-contracts/SKILL.md`

**Se activa cuando:** se crean o modifican modelos, schemas Pydantic, repositorios, exports
JSON, migraciones o campos de reportes.

**Conocimiento que encapsula:**

- Enums cerrados en minúsculas (finding_type, severity, confidence, detector_method,
  reasoning_depth, run.status, extraction_status, skip_reason) y la regla de no añadir valores
  sin actualizar `.aicontext/tasks/README.md`.
- Los 5 modelos SQLModel (`Run`, `Asset`, `RawMetadataItem`, `Finding`, `AgentLog`) con sus
  particularidades: UUIDs como str, `RawMetadataItem.id` autoincrement, `value` siempre texto
  sanitizado, campos de prosa Optional.
- Ciclo de vida de un finding: detectores (severity NULL) → heurístico (baseline + plantillas)
  → agente (ajusta dentro de la rúbrica) → reportes (funcionan con cualquiera de los dos).
- Dedup: fórmula `sha256(asset_id:finding_type:snippet.strip().lower())`, unique constraint,
  `field_source` concatenado con `" | "`.
- Idiomas por capa: reportes y CLI en inglés, Web UI en español, documentación en español.
- **Ciclo de vida del dato personal** (amenaza 14): minimización en origen, `value` siempre
  texto, DB y reportes fuera de la imagen y del repo, sin envío a terceros, snippet (no campo
  completo) al LLM.

**Amenazas que cubre:** 13, 14.

**Lo usan:** `pipeline-engineer`, `llm-agent-engineer` (enums de `AgentFindingEvaluation`) y
`ui-engineer` (enums que devuelven la API y la tabla de findings).

**Fuente:** `.aicontext/tasks/README.md` (contratos compartidos), `00-architecture-and-safety.md`
(0.2).

---

### 2.3 `metatracer-supply-chain` — Transversal · Prioridad crítica · **Creado**

**Ubicación:** `.cursor/skills/metatracer-supply-chain/SKILL.md`

**Se activa cuando:** se toca `pyproject.toml`, el `Dockerfile`, `docker-compose.yml`,
`.dockerignore` o `.env.example`, y antes de añadir cualquier import de un paquete de terceros.

**Por qué existe:** era la única amenaza del modelo sin skill que la documentara. Dependía por
completo de que `safety-guardian` se acordara de auditar las dependencias, sin un sitio donde
consultar la lista aprobada ni el procedimiento.

**Conocimiento que encapsula:**

- La lista cerrada de TASK-00 (0.1.3) con las versiones mínimas exactas, runtime y dev
  separadas, y `requires-python = ">=3.11,<3.13"`.
- Separación runtime/dev con consecuencia real: `reportlab`, `pytest` y `ruff` nunca se importan
  desde `src/`; hacerlo convertiría una dependencia de test en dependencia de producto.
- Checklist de 8 puntos antes de añadir una dependencia: stdlib primero, comprobar solape con
  lo ya aprobado, nombre exacto en PyPI (typosquatting: `pillow`/`pillow-simd`,
  `piexif`/`pyexif`), mantenimiento y licencia, código en import time, extensiones nativas,
  runtime vs dev, y sincronizar `pyproject.toml` con TASK-00 en el mismo cambio.
- Prohibiciones: instalar o descargar código en runtime, `curl | sh` en el `Dockerfile`, cargar
  plugins de terceros, y fijar una versión máxima para esquivar un fallo en vez de arreglarlo.
- Superficie de la imagen (TASK-07, 7.3): multi-stage sin compiladores en el stage final, solo
  `libjpeg`+`zlib`, usuario no-root, `.dockerignore` con `.env`/`.git`/`data/*.db`/`.venv`,
  volúmenes solo `data/` y `reports/`, Compose sin `ALLOW_LOOPBACK`.
- Secretos: `.env` nunca versionado ni dentro de la imagen; `.env.example` con nombres, jamás
  valores.
- **Assets de terceros de la UI (cerrado en TASK-26, reactivado en T11):** Tailwind y Alpine
  eran cadena de suministro ejecutándose en el navegador del hunter. Desde el rediseño
  (2026-09-21) no hubo CDN: Tailwind compilado offline y Alpine CSP vendorizado. **T11 retiró
  V1 por completo**; Web V2 empaqueta Tailwind 4 y Radix/Lucide en el bundle de Next, sin CDN
  ni `<script src>` de terceros. Regla vigente (sigue aplicando): nunca re-introducir un
  script de terceros, ni `@latest`, ni orígenes adicionales (fuentes, iconos remotos).
- Huecos conocidos de la lista, empezando por `langchain-openai` (ver §3.4). **Resuelto:** aprobada y en producción desde TASK-05.

**Amenazas que cubre:** 15.

**Lo usan:** `pipeline-engineer` (dueño de `pyproject.toml`), `test-engineer` (dueño de la
imagen), `ui-engineer` (assets de CDN) y `safety-guardian` (auditoría con veto).

**Fuente:** `.aicontext/tasks/00-architecture-and-safety.md` (0.1.3),
`07-testing-and-deployment.md` (7.3), `06-interfaces.md` (stack de la Web UI).

---

### 2.4 `metadata-extraction` — TASK-01 + TASK-09 · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/metadata-extraction/SKILL.md`

**Se activa cuando:** se trabaja en `extractors/`, el crawler o el cliente HTTP de descarga.

**Conocimiento que encapsula:**

- `TargetResolver`: clasificación de entrada (archivo / página / dominio) con validación de
  scope previa; dominio sin esquema → `https://{domain}/`. Una URL que acaba en `.js` es
  `TargetKind.file` (TASK-09).
- `PublicDocCrawler`: profundidad 1, parseo con BeautifulSoup (`<a href>`, `<img src>`,
  `<script src>` in-scope que termina en `.js`), extensiones aceptadas, descarte inmediato de
  hosts off-scope y esquemas `javascript:`/`data:`/`mailto:`, topes (5 MB HTML,
  `MAX_ASSETS_PER_RUN`=50; la página HTML cuenta contra el cap). El body crawleado se
  devuelve para persistir el asset **sin segundo GET**.
- Allowlist por magic bytes (PDF `%PDF`, JPEG `FF D8 FF`, PNG, TIFF, WEBP RIFF) — no fiarse de
  la extensión ni del Content-Type solo. HTML/JS se clasifican por content-type/path **después**
  de fallar el magic. URL con extensión de documento cuyo body sea HTML → `unsupported_type`.
- `PdfMetadataExtractor`: InfoDict → namespace `pdfinfo`, fechas `D:YYYYMMDDHHmmSS` → ISO 8601
  cuando sea parseable, XMP (`dc:`, `pdf:`, `photoshop:`, `xmp:`, `xmpMM:`), PDF cifrado o
  dañado → `failed` sin romper el run.
- `ImageMetadataExtractor`: EXIF con Pillow/piexif (TAGS/GPSTAGS), bloque GPS crudo intacto
  (la conversión a decimal es del detector), IPTC/XMP en JPEG/PNG/WebP.
- TASK-09: `HtmlMetadataExtractor` (title / meta allowlist / comentarios, salta `<!--[if`),
  `extract_http_headers` (allowlist de recon; denylist de cookies/Authorization),
  `JavaScriptMetadataExtractor` (parser de `//` y `/* */` que salta strings; `https://` no es
  comentario). Namespaces `html` / `http` / `js`. TASK-37: `OfficeMetadataExtractor` lee
  `docProps/*.xml` / `meta.xml` (`ooxml`/`odf`) y nunca el cuerpo. Cero body persistido.
- Sanitización: tuplas/`IFDRational`/bytes → string UTF-8 o JSON corto; nunca blobs
  (thumbnails, ICC, HTML/JS fuente); truncar >2 KB con `[truncated]`.
- Ciclo de vida del asset: crear `Asset` antes de extraer, borrar el temporal en `finally`
  (PDF/imagen; HTML/JS se extraen en memoria), hash SHA-256 para `duplicate_hash`, recalcular
  `Run.total_assets`.

**Amenazas que cubre:** 1, 2, 4, 5, 13.

**Lo usan:** `pipeline-engineer` (núcleo) y `safety-guardian` al revisar el crawler o los
extractores. Recomendable para `test-engineer` al generar fixtures (ver §3.1).

**Fuente:** `.aicontext/tasks/01-metadata-extraction.md`, `.aicontext/tasks/09-source-expansion.md`.

---

### 2.5 `detector-patterns` — TASK-02 · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/detector-patterns/SKILL.md`

**Se activa cuando:** se escriben o ajustan detectores o el `FindingConsolidator`.

**Conocimiento que encapsula:**

- Contrato `Detector` (Protocol): entrada solo `RawMetadataItem` estructurado (prohibido abrir
  el archivo original), salida `FindingDraft` con `detector_method="rule"` y severity NULL.
- `GpsDetector`: DMS → decimal WGS84, hemisferios S/W negativos, no reaplicar si ya es
  decimal, filtros de rango, descarte de `(0,0)` y no finitos.
- `EmailDetector`: regex práctica (no RFC 5322), blacklist de dominios de herramienta
  (`adobe.com`, `apple.com`...), confidence según si el email es el campo o está embebido.
- `InternalPathDetector`: Windows drive, UNC, Unix/macOS; `/opt` y `/usr` genéricos NO;
  negativos (`http://`, `xmlns:`, rutas relativas); ante la duda, no emitir (la rúbrica
  prefiere infra-detección a ruido).
- `SoftwareVersionDetector`: nombre + versión numérica obligatoria; `Microsoft Word` sin
  versión NO es finding; nada de findings `info` "por si acaso". TASK-09: también escanea
  cabeceras de recon (`server`, `x-powered-by`, `generator`, …); en `x-aspnet-version` y
  similares el número solo basta (el nombre del header identifica el stack).
- `DebugCommentDetector`: keywords fuertes (`TODO:`, `FIXME:`, tickets `JIRA-\d+`...) vs.
  débiles (`CONFIDENTIAL`, `DRAFT`); un finding por campo, no por keyword. Las claves
  `comment` / `description` cubren `html:comment` y `js:comment` sin detector nuevo.
- TASK-37: `InternalEndpointDetector` (RFC1918 y hostnames internos) y
  `CloudStorageDetector` (S3/GCS/Azure/R2, sin query; la URL no se pide). Sin severity.
- `FindingConsolidator`: firma de dedup, insert ignorando conflictos, actualización de
  `Run.total_findings`.
- Normalización de texto (strip, NFC) y snippet máx. ~150 chars (GPS: una línea).
- **Coste de las regex:** cuantificadores acotados y sin anidar, sobre entrada ya truncada. Las
  regex corren contra valores que escribió el target.

**Amenazas que cubre:** 6.

**Lo usan:** `pipeline-engineer` (núcleo). Recomendable para `test-engineer` al escribir los
casos negativos de cada detector.

**Fuente:** `.aicontext/tasks/02-specific-detection.md`, `.aicontext/tasks/37-new-detectors.md`.

---

### 2.6 `risk-rubric` — TASK-03 (+ prompts de TASK-05) · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/risk-rubric/SKILL.md`

**Se activa cuando:** se implementa el clasificador heurístico, las plantillas de
impacto/remediación, o los prompts y validadores del agente.

**Conocimiento que encapsula:**

- La rúbrica contextual completa (critical/high/medium/low/info) con ejemplos válidos y "lo
  que no basta" para cada nivel.
- Techos heurísticos obligatorios: GPS máx. `high`; `software_version` máx. `low`; email máx.
  `medium`; `internal_path` con username/UNC → `high`, `/var/www` sin usuario → `medium`;
  `debug_comment` con valor de secreto en el snippet → `critical`; `secret` (AKIA / `ghp_` / PEM / JWT) → `critical`.
- Anclaje anti-alucinación: snippet vacío o no substring de la metadata → `info`; ante
  ambigüedad, un nivel menos; prohibido subir sin texto que lo justifique.
- `HeuristicRiskClassifier`: sin I/O, determinista (mismos inputs → misma salida), plantillas
  fijas en inglés por tipo+nivel, repro no explotativo (`exiftool`/`pdfinfo`/`curl` sobre el
  archivo público).
- Uso dual: la misma rúbrica va en el system prompt del agente y en el validador post-LLM (el
  guard solo puede bajar o rechazar, nunca subir por encima del techo sin evidencia nueva).

**Amenazas que cubre:** 7 (el techo de severidad es lo que impide que texto del target infle un
finding).

**Lo usan:** `pipeline-engineer` (núcleo en TASK-03: heurístico y plantillas) y
`llm-agent-engineer` (núcleo en TASK-05: prompts y guard). **Skill de doble dueño**: cualquier
cambio en la rúbrica afecta a los dos lados y debe mantenerlos coherentes.

**Fuente:** `.aicontext/tasks/03-risk-classification.md`.

---

### 2.7 `langgraph-agent-patterns` — TASK-05 · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/langgraph-agent-patterns/SKILL.md`

**Se activa cuando:** se trabaja en `agents/`, prompts o `AgentLog`.

**Conocimiento que encapsula:**

- `ContextOptimizer`: payload máximo por finding (los 8 campos del contrato, nada más), keys
  vacías fuera, tope ~1.500 tokens por llamada (`len(text)//4`), priorización de recorte por
  tipo (gps → internal_path → debug_comment → email → software_version).
- `AgentFindingEvaluation` (Pydantic): severity, justification, impact_analysis, remediation,
  reproduction_steps, cited_evidence, title; `with_structured_output`; un reintento y luego
  fallback si el schema no se cumple.
- Routing de modelos: fuerte (`LLM_MODEL`, Kimi/Moonshot) para análisis/severidad; rápido
  (`FAST_MODEL`) para títulos y summary ejecutivo; cliente LangChain `ChatOpenAI` contra
  `LLM_BASE_URL`.
- Prompts versionados en `src/metatracer/agents/prompts/` con la rúbrica y las prohibiciones
  (no CVEs inventados, no exploits, no hechos fuera del payload, no GPS a critical sin texto).
- Invariantes del validador post-LLM: `cited_evidence` substring de `evidence_snippet`
  (casefold, whitespace colapsado); ni `finding_type` ni `evidence_snippet` mutables;
  desescalado al techo heurístico; lista de palabras prohibidas en `reproduction_steps`.
- **El payload es dato, nunca instrucción:** los campos EXIF/XMP los escribió el target, así que
  el validador determinista —no la redacción del prompt— es la garantía real.
- `MetaTracerGraph`: estado `AgentState`, nodos (LoadNext → Analyze → Classify → Draft →
  Save, y SynthesizeReportSummary al agotar), verbosidad por `reasoning_depth`.
- Resiliencia: `tenacity` (3 reintentos, backoff exponencial con jitter sobre 429/500/
  timeout); clave vacía o fallo agotado → `HeuristicRiskClassifier` con
  `agent_model_used="heuristic-fallback"`; el finding nunca se borra.
- Higiene de secretos en `AgentLog`: tokens, modelo y latencia sí; clave de API, cabeceras de
  auth y prompt completo, nunca.
- Tests con LLM fake (`FakeListLLM` o JSON fijo); cero APIs reales en CI.

**Amenazas que cubre:** 7, 8, 9.

**Lo usan:** `llm-agent-engineer` (núcleo). Recomendable para `test-engineer` al construir los
mocks del grafo.

**Fuente:** `.aicontext/tasks/05-ai-agents.md`.

---

### 2.8 `report-engine` — TASK-04 · Prioridad media · **Creado**

**Ubicación:** `.cursor/skills/report-engine/SKILL.md`

**Se activa cuando:** se trabaja en `reports/` o en la exportación.

**Conocimiento que encapsula:**

- `ReportBuilder`: orden (severity critical→info, NULLs al final; confidence; discovered_at),
  cabecera (título, target, scope, run_id, timestamp UTC, reasoning_depth, executive summary,
  Scope & Compliance Notice), run vacío → archivo válido con mensaje de cero hallazgos.
- Ficha por finding en inglés, orden fijo de 9 campos (Title → Remediation), evidence en
  bloque de código byte-a-byte igual al persistido, repro no explotativo.
- `MarkdownReportExporter`: GFM, heading `### [High] ...`, plantilla exacta de la ficha.
- `JsonReportExporter`: schema Pydantic validado con `model_validate` antes de escribir, enums
  en minúsculas, `reproduction_steps` como `list[str]`, `compliance_notice`.
- `HtmlReportExporter` (TASK-08): el mismo `ReportData`, evidencia escapada, compliance notice;
  se imprime a PDF si hace falta (cero dependencia runtime de PDF).
- Nomenclatura de archivos: `metatracer-{slug}-{run_id_short}-{YYYYMMDDTHHMMSSZ}.md/.json/.html`;
  slug saneado y escritura confinada al directorio de salida; sin tabla `Report` en SQLite (se
  regenera desde findings).
- **Evidencia hostil en Markdown:** el snippet puede contener backticks o saltos de línea; el
  cercado del bloque no puede romperse ni alterar los bytes de la evidencia.
- Independencia de TASK-05: campos de prosa vacíos → `Not generated (heuristic baseline)`,
  nunca crash.
- TASK-39: `apply_redaction` reescribe el `ReportData` del fichero (`none`/`contacts`/
  `coordinates`/`all`); la BD no cambia. API/CLI default `none`; UI propone `contacts`.

**Amenazas que cubre:** 10, 11, 14 (compliance notice).

**Lo usan:** `pipeline-engineer` (núcleo), `ui-engineer` (endpoints de export).

**Fuente:** `.aicontext/tasks/04-report-generation.md`, `.aicontext/tasks/08-usability.md`,
`.aicontext/tasks/39-export-redaction.md`.

---

### 2.9 `metatracer-ui` — TASK-06 + TASK-20 + TASK-26 · Prioridad media · **Creado**

**Ubicación:** `.cursor/skills/metatracer-ui/SKILL.md`

**Se activa cuando:** se trabaja en `services/`, `api/`, `cli/` o templates/estáticos, y en
cualquier rediseño de la Web UI.

**Conocimiento que encapsula:**

- `ScanOrchestratorService`: secuencia fija de 9 pasos, un scan activo por proceso (409 si hay
  run `running`), excepciones de safety abortan, asset fallido no.
- `ProgressEvent`/`ProgressStage`: mismo callback/cola asyncio para CLI y SSE.
- CLI Typer/Rich: comandos (`scan`, `report`, `list-runs`), flags de scope (`-s` repetible
  obligatorio, `-y`, `-d`, `-o`, `-f`), prompt de confirmación con default `N`, banner ético,
  tabla coloreada por severidad, exit codes (0 si termina, 1 si error fatal).
- API FastAPI: contratos de los 5 endpoints (`POST /api/runs` 202/403/409, `GET` status, SSE
  stream, findings con filtro, export attachment), bind `127.0.0.1` por defecto, auth opcional
  desde TASK-24 (`METATRACER_AUTH_ENABLED`; roles `operator`/`viewer`).
- **Web UI (stack real tras T11):** Next.js 16 + React 19 + Tailwind 4 en `web/`, servida
  desde la raíz del origen por Caddy (`deploy/Caddyfile`). **Web V1 (Jinja + Alpine) fue
  retirada**: no quedan plantillas, `api/pages.py` ni `/static` de V1; FastAPI es solo-API.
  Tokens `.mt-*` como CSS variables, TanStack Query para datos de servidor, Zod en fronteras
  de formulario, primitivas Radix + Lucide empaquetadas (sin CDN).
- **Renderizado de contenido del target:** prohibido `dangerouslySetInnerHTML` y cualquier
  markdown-a-HTML; todo dato va como nodo de texto; URLs de asset solo por `safeUrl()`.
- **Cadena de suministro de la UI:** cero scripts de terceros en runtime; todo empaquetado
  en el bundle de Next (sin CDN); iconos SVG inline; cabeceras del shell en
  `web/next.config.ts` (sin `unsafe-eval` en producción) y las de la API en
  `api/security_headers.py` (sin orígenes de terceros, HSTS tras proxy TLS).
- Paridad: CLI y UI muestran los mismos findings/severidades para el mismo `run_id`.

**Amenazas que cubre:** 10, 11, 12, 15.

**Lo usan:** `v2-ui-engineer` (núcleo Web), `ui-engineer` (API/CLI), `ui-architect` (contratos V2)
y `safety-guardian` (CSP / `safeUrl`).

**Fuente:** `.aicontext/tasks/06-interfaces.md`, `.aicontext/tasks/20-ui-polish.md`,
`.aicontext/tasks/26-ui-redesign.md`, `.aicontext/ui/`.

---

### 2.10 `metatracer-testing` — TASK-07 (+ tests de cada slice) · Prioridad media · **Creado**

**Ubicación:** `.cursor/skills/metatracer-testing/SKILL.md`

**Se activa cuando:** se escriben tests, fixtures, e2e o Docker.

**Conocimiento que encapsula:**

- Factory de fixtures (`tests/fixtures/generate_test_fixtures.py`): los 6 casos (JPEG GPS,
  PDF email, PDF path, PDF software, PDF/JPEG debug, limpio) con Pillow/piexif/reportlab/pypdf;
  dominio sintético `acme-corp.internal` (`.test` no es un buzón; TASK-34).
- Servidor mock HTTP (ASGI/uvicorn en puerto efímero) que sirve fixtures y una página que los
  enlaza; cero sitios de terceros en CI.
- Conflicto loopback: `METATRACER_ALLOW_LOOPBACK=true` solo en el proceso de test
  (monkeypatch/env), con test que demuestra que sin el flag el mock local es rechazado; el
  flag no se documenta como feature de usuario.
- Marcas pytest (`unit`, `integration`, `e2e`, `slow`) y cobertura ≥85% en
  `core`/`detectors`/`extractors`/`reports` (sin inflar con tests triviales de prompts).
- E2E `test_e2e_pipeline.py`: mock origin → discover → extract → detect → classify → report;
  criterios del PRD (4 de 5 tipos mínimo, Markdown con evidence/impact/remediation, filas en
  SQLite).
- Docker: multi-stage `python:3.12-slim`, libjpeg+zlib, usuario no-root, entrypoint `web` |
  CLI, `.dockerignore`, Compose con volúmenes y env (sin `ALLOW_LOOPBACK`), CLI efímera con
  `docker run`, scripts `docker-metatracer.ps1`/`.sh`, healthcheck.
- **Nunca se mockea un control de safety** para que un test pase: si el guard estorba, el test
  está mal planteado.

**Amenazas que cubre:** 3, 5, 14, y el meta-riesgo de que un test verde oculte un control roto.

**Lo usan:** `test-engineer` (núcleo), y cualquier agente al cerrar el DoD de su task.

**Fuente:** `.aicontext/tasks/07-testing-and-deployment.md`.

---

### 2.11 `metatracer-sdd` — Overlay · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/metatracer-sdd/SKILL.md`

**Se activa cuando:** se escribe o cambia `specs/`, `MEMORY.md`, `.aicontext/tasks/` o se abre TASK-36+.

**Conocimiento:** ritual reserved → active → enum → task → skill → código → línea en MEMORY.
No forkear enums. No implementar reserved.

**Amenazas:** ninguna nueva; evita implementar Fase 3–5 sin contrato.

**Lo usan:** `docs-architect` (núcleo). Recomendada para cualquier ingeniero al abrir slice.

**Fuente:** `specs/README.md`, `specs/00-sdd-governance.md`.

---

### 2.12 `metatracer-platform` — TASK-22–35 · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/metatracer-platform/SKILL.md`

**Se activa cuando:** se toca watch, Postgres/Alembic/pgvector, auth/CSRF, webhooks HMAC, triage o retención.

**Conocimiento:** comportamiento **ya existente**. Watch `--cron` = spec 44. Leftover: deltas desaparecido/severity-up. ONNX = spec 40.

**Amenazas:** 1, 14, 15 (egreso, PII, deps).

**Lo usan:** `pipeline-engineer`, `ui-engineer`, `llm-agent-engineer` (retriever), `safety-guardian` al revisar auth/webhooks.

**Fuente:** TASK-22–35, `features/12-platform-v3.md`.

---

### 2.13 `metatracer-investigations` — TASK-36 · Prioridad alta · **Creado**

**Ubicación:** `.cursor/skills/metatracer-investigations/SKILL.md`

**Se activa cuando:** se toca `services/investigation.py`, correlación, `api/investigations.py`, CLI `investigation` o TASK-36.

**Conocimiento:** agrupa runs, no aísla; sugerencia de triage no se aplica; `value_hash` no es identidad.

**Lo usan:** `pipeline-engineer`, `ui-engineer` (CLI).

**Fuente:** TASK-36, spec 36.

---

### 2.14 `metatracer-onnx` — TASK-40 · Prioridad media · **Creado**

**Ubicación:** `.cursor/skills/metatracer-onnx/SKILL.md`

**Se activa cuando:** se toca `agents/embeddings.py`, `_embed` de pgvector o el extra `[onnx]`.

**Conocimiento:** MiniLM local 384-d; fallback hashing-trick; cero red; no va en la imagen default.

**Lo usan:** `llm-agent-engineer`, `safety-guardian` (deps).

**Fuente:** TASK-40, spec 40.

---

## 3. Trazabilidad

### 3.1 Matriz skill × agente

La **fuente de verdad** de qué carga cada agente es su propio archivo en `.cursor/agents/`, que
enumera su contexto en la sección "Contexto que debes cargar". Esta matriz refleja lo declarado
allí; si divergen, manda el archivo del agente y esta tabla se corrige.

Leyenda: `N` = núcleo · `S` = soporte declarado · vacío = no aplica.

| Skill | safety-guardian | pipeline-engineer | llm-agent-engineer | ui-engineer | ui-architect | v2-ui-engineer | test-engineer | docs-architect |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `metatracer-safety-rules` | N | S | | | S | | S (bypass loopback) | |
| `metatracer-data-contracts` | | S | S | S | S | S | | |
| `metatracer-supply-chain` | N (auditoría) | S (`pyproject.toml`) | | S | S | S (bundle) | S (imagen) | |
| `metadata-extraction` | S (crawler) | N | | | | | S (fixtures) | |
| `detector-patterns` | | N | | | | | S (negativos) | |
| `risk-rubric` | | N | N | | | | | |
| `langgraph-agent-patterns` | | | N | | | | S (mocks) | |
| `report-engine` | | N | | S | | | | |
| `metatracer-ui` | | | | S (API/CLI) | N | N | | |
| `metatracer-testing` | | S (DoD) | S (DoD) | S (DoD) | | S (DoD) | N | |
| `metatracer-sdd` | | S | S | S | | S | | N |
| `metatracer-platform` | S (auth/webhook) | S | S (retriever) | S | | | | |
| `metatracer-investigations` | | S | | S (CLI) | | | | |

Notas de lectura:

- Las **rules** aplican siempre a los ocho agentes. Un agente puede no cargar
  `metatracer-data-contracts` y aun así conocer los enums.
- `risk-rubric` es la única skill de producto con **dos núcleos** (heurístico y agente).
- `docs-architect` carga `metatracer-sdd`; no carga skills de módulo de producto.
- `metatracer-ui` tiene dos núcleos: `ui-architect` (contratos V2) y `v2-ui-engineer` (código).

### 3.2 Orden de creación por slice

Alineado con las fases de [tasks/README.md](../.aicontext/tasks/README.md).

| Slice | Tasks | Skills a crear | Estado |
| :--- | :--- | :--- | :--- |
| 1 | TASK-00 | `metatracer-safety-rules`, `metatracer-data-contracts`, `metatracer-supply-chain` | Creadas |
| 2 | TASK-01, TASK-02 | `metadata-extraction`, `detector-patterns` | Ambas **creadas** |
| 3 | TASK-03, TASK-05 | `risk-rubric`, `langgraph-agent-patterns` | Ambas **creadas** |
| 4 | TASK-04, TASK-06 | `report-engine`, `metatracer-ui` | Ambas **creadas** (`report-engine` en T5, `metatracer-ui` en TASK-26) |
| 5 | TASK-07 | `metatracer-testing` | **Creada** |
| 6 | TASK-08 | (reusa `metatracer-ui`, `report-engine`, guard de TASK-05) | v1.1 cerrada; sin skill nueva |
| 7 | TASK-09 | (reusa `metadata-extraction` / `detector-patterns`) | v1.2 cerrada; skills materializadas |
| 8 | TASK-20, TASK-26, T11 | (reusa `metatracer-ui`) | Web V2 vigente; skill actualizada |
| 9 | overlay SDD | `metatracer-sdd`, `metatracer-platform` | Creadas 2026-11-05 |

Un agente sin su skill no está roto: funciona con las rules y su propio prompt. Con la skill,
además conoce los valores exactos del módulo y sus trampas conocidas.

### 3.3 Cobertura del modelo de amenazas

Cruce de las diez skills con [§4.2 de agents.md](agents.md#42-modelo-de-amenazas-que-todo-agente-lleva-encima).
Sirve para detectar amenazas que ninguna skill documenta y que, por tanto, dependen solo del
criterio del agente o de la revisión. **Toda amenaza debe tener al menos una skill**: cuando una
se queda sin dueño documental, su mitigación depende de que alguien se acuerde.

| Amenaza | Skill que la documenta |
| :--- | :--- |
| 1 SSRF / red interna | `metatracer-safety-rules`, `metadata-extraction` |
| 2 Redirect fuera de scope | `metatracer-safety-rules`, `metadata-extraction` |
| 3 DNS rebinding / TOCTOU | `metatracer-safety-rules`, `metatracer-testing` |
| 4 Tipo de archivo mentido | `metadata-extraction` |
| 5 Bombas de tamaño / descompresión | `metadata-extraction`, `metatracer-testing` |
| 6 ReDoS en detectores | `detector-patterns` |
| 7 Prompt injection vía metadata | `langgraph-agent-patterns`, `risk-rubric` |
| 8 Fuga de secretos | `langgraph-agent-patterns` |
| 9 Denial of wallet | `langgraph-agent-patterns` |
| 10 Escritura fuera de `reports/` | `report-engine`, `metatracer-ui` |
| 11 Ruptura del bloque de evidencia | `report-engine`, `metatracer-ui` |
| 12 XSS en la Web UI | `metatracer-ui` |
| 13 Log injection | `metatracer-safety-rules` |
| 14 Datos personales | `metatracer-data-contracts`, `report-engine`, `metatracer-testing` |
| 15 Cadena de suministro | `metatracer-supply-chain`, `metatracer-ui` |

Las quince amenazas tienen ya al menos una skill que las documenta. La 13 tiene su formato
fijado en `metatracer-safety-rules` (sección "Logging seguro") y la 14 su ciclo de vida en
`metatracer-data-contracts` (sección "Ciclo de vida del dato personal"). Ninguna queda ya
cubierta solo de forma indirecta.

### 3.4 Dependencias pendientes de aprobación

Consecuencia de tener lista cerrada: cuando una task posterior necesita algo que TASK-00 no
declaró, es una decisión, no un detalle de implementación.

| Necesidad | Task que la pide | Estado |
| :--- | :--- | :--- |
| `langchain-openai` (clase `ChatOpenAI`) | TASK-05 (5.2.2) | **Aprobada y en producción** — presente en `pyproject.toml` (con techo `openai<3` y pin de `langsmith`); TASK-05 cerrada. El hueco documentado aquí queda resuelto |

Este hueco no se resuelve dentro del código: aplica el protocolo de escalado
([agents.md §4.4](agents.md#44-protocolo-de-escalado-cuándo-parar-y-preguntar)).

---

## 4. Convenciones de autoría de las skills

### 4.1 Plantilla

Al materializar cada skill en `.cursor/skills/<nombre>/SKILL.md`, este es el esqueleto (el
frontmatter usa solo `name` y `description`, igual que las cuatro skills ya creadas):

```markdown
---
name: nombre-en-kebab-case
description: <QUÉ hace, en tercera persona>. Usar al <CUÁNDO: módulos, clases y tasks concretas>.
---

# Título corto

Una o dos frases de encuadre. Referencia completa: `.aicontext/tasks/XX-*.md` (subtarea N).

## <Componente o decisión 1>

- Valores exactos, umbrales, regex, límites.
- Trampas conocidas y su motivo.

## <Componente o decisión 2>

...

## Checklist de revisión

- [ ] Punto verificable 1
- [ ] Punto verificable 2
```

La `description` es lo que dispara la carga just-in-time: debe contener los **términos trigger**
que aparecerán en la petición del usuario o en el código (nombres de clase, carpeta, task).
Una descripción vaga significa una skill que nunca se activa.

### 4.2 Reglas

1. **Frontmatter:** `name` en kebab-case coincidiendo con la carpeta; `description` en tercera
   persona con QUÉ hace y CUÁNDO usarla.
2. **Concisión:** el agente ya es capaz; solo se documenta lo que no puede saber (decisiones
   del PRD, valores exactos, trampas conocidas). Cuerpo <500 líneas, idealmente <150.
3. **Progressive disclosure:** lo esencial en `SKILL.md`; si hiciera falta más, archivos
   `reference.md`/`examples.md` a un solo nivel de profundidad.
4. **Referencias, no copias:** apuntar a `.aicontext/tasks/XX-*.md` como fuente de verdad.
5. **No duplicar capas:** no repetir la rule ni explicar cómo debe comportarse el agente (§1.1).
6. **Sin rutas Windows** en los ejemplos (`scripts/helper.py`, no `scripts\helper.py`).
7. **Sin información volátil:** nada de "usa la API v2 si estás antes de tal fecha".
8. **Idioma:** español (documentación), conservando en inglés identificadores, enums y
   literales de código.
9. **Ejemplos en pares mal/bien** cuando la trampa sea sutil; el contraste enseña más que la
   descripción.

### 4.3 Anti-patrones de autoría

- Skill genérica que valdría para cualquier proyecto Python ("buenas prácticas de asyncio").
- Copiar la task entera dentro del `SKILL.md`: se desincroniza en la primera revisión del PRD.
- Repetir una regla inviolable en lugar de referenciar la rule que ya la impone siempre.
- Mezclar rol y conocimiento ("eres un ingeniero cuidadoso…"): eso pertenece al prompt del
  agente.
- Descripción sin términos trigger, que hace la skill invisible.
- Incluir valores que aún no están decididos en el backlog: primero se decide en `.aicontext/`.

### 4.4 Definition of Done de una skill

- [ ] Vive en `.cursor/skills/<nombre>/SKILL.md` con `name` igual al nombre de la carpeta.
- [ ] La `description` dice QUÉ y CUÁNDO, con términos trigger reales.
- [ ] Todo valor exacto que contiene coincide con su task de origen (verificado, no recordado).
- [ ] No duplica una rule ni el prompt de un agente.
- [ ] Su ficha de este catálogo está actualizada: amenazas cubiertas, quién la usa y fuente.
- [ ] La matriz de §3.1 refleja qué agentes la declaran.
- [ ] Comprobada en la práctica: una petición típica del módulo la activa.
