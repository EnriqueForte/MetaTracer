# Agentes y capacidades para MetaTracer

**Proyecto:** MetaTracer — AI-powered sensitive metadata discovery for Bug Bounty & Red Team
**PRD:** [índice](../.aicontext/PRD.md) · **Backlog:** [tasks](../.aicontext/tasks/README.md)
**Documento hermano:** [skills.md](skills.md) (define las skills; este define los agentes)
**Versión:** 1.6
**Estado:** Operativo — 2 rules, **10 skills materializadas** (catálogo completo: 3 transversales + `metatracer-ui` + `detector-patterns`, `risk-rubric`, `report-engine`, `metadata-extraction`, `langgraph-agent-patterns`, `metatracer-testing`) y los **8 subagentes** (incluye `ui-architect` y `v2-ui-engineer`); backlog `TASK-00` → `TASK-35` (v1.0 → v3.2, cerradas 2026-10-05; suite 787 passed, cobertura 91.30%). El retoque de Web V2 está planificado en `.aicontext/architecture/v2-ui-refresh.md` y no es una task del backlog Jinja.
**Fecha:** 24 de octubre de 2026 (T5b: catálogo de skills completo)

Este documento define qué capacidades (rules, skills) y qué agentes (subagentes) necesita el
desarrollo de MetaTracer, derivados del análisis del PRD y del backlog `TASK-00` → `TASK-35`.

MetaTracer es una herramienta de seguridad ofensiva **autorizada**: escanea assets públicos de
targets que no controlamos, guarda datos personales (GPS, emails) y pasa texto escrito por el
target a un LLM. Por eso los agentes que la construyen no se juzgan solo por si "el código
funciona", sino por si el código **falla cerrado** cuando algo va mal.

Este archivo es el **índice y el contrato común** de toda la configuración: §0 dice dónde está
cada cosa, §4 es el perfil que comparten todos los agentes, y §5 enlaza cada agente concreto.

---

## 0. Mapa de archivos

Toda la configuración se navega desde aquí, aunque no toda pueda vivir en la misma carpeta.

### Artefactos funcionales (los carga Cursor)

| Artefacto | Ruta real | Enlace |
| :--- | :--- | :--- |
| Rule — reglas inviolables | `.cursor/rules/safety-invariants.mdc` | [ver](../.cursor/rules/safety-invariants.mdc) |
| Rule — contratos de datos | `.cursor/rules/data-contracts.mdc` | [ver](../.cursor/rules/data-contracts.mdc) |
| Skill — safety rules | `.cursor/skills/metatracer-safety-rules/SKILL.md` | [ver](../.cursor/skills/metatracer-safety-rules/SKILL.md) |
| Skill — data contracts | `.cursor/skills/metatracer-data-contracts/SKILL.md` | [ver](../.cursor/skills/metatracer-data-contracts/SKILL.md) |
| Skill — supply chain | `.cursor/skills/metatracer-supply-chain/SKILL.md` | [ver](../.cursor/skills/metatracer-supply-chain/SKILL.md) |
| Skill — UI | `.cursor/skills/metatracer-ui/SKILL.md` | [ver](../.cursor/skills/metatracer-ui/SKILL.md) |
| Skill — detector patterns | `.cursor/skills/detector-patterns/SKILL.md` | [ver](../.cursor/skills/detector-patterns/SKILL.md) |
| Skill — risk rubric | `.cursor/skills/risk-rubric/SKILL.md` | [ver](../.cursor/skills/risk-rubric/SKILL.md) |
| Skill — report engine | `.cursor/skills/report-engine/SKILL.md` | [ver](../.cursor/skills/report-engine/SKILL.md) |
| Skill — metadata extraction | `.cursor/skills/metadata-extraction/SKILL.md` | [ver](../.cursor/skills/metadata-extraction/SKILL.md) |
| Skill — langgraph agent patterns | `.cursor/skills/langgraph-agent-patterns/SKILL.md` | [ver](../.cursor/skills/langgraph-agent-patterns/SKILL.md) |
| Skill — testing | `.cursor/skills/metatracer-testing/SKILL.md` | [ver](../.cursor/skills/metatracer-testing/SKILL.md) |
| Subagente — safety-guardian | `.cursor/agents/safety-guardian.md` | [ver](../.cursor/agents/safety-guardian.md) |
| Subagente — pipeline-engineer | `.cursor/agents/pipeline-engineer.md` | [ver](../.cursor/agents/pipeline-engineer.md) |
| Subagente — llm-agent-engineer | `.cursor/agents/llm-agent-engineer.md` | [ver](../.cursor/agents/llm-agent-engineer.md) |
| Subagente — ui-engineer | `.cursor/agents/ui-engineer.md` | [ver](../.cursor/agents/ui-engineer.md) |
| Subagente — ui-architect | `.cursor/agents/ui-architect.md` | [ver](../.cursor/agents/ui-architect.md) |
| Subagente — v2-ui-engineer | `.cursor/agents/v2-ui-engineer.md` | [ver](../.cursor/agents/v2-ui-engineer.md) |
| Subagente — test-engineer | `.cursor/agents/test-engineer.md` | [ver](../.cursor/agents/test-engineer.md) |
| Subagente — docs-architect | `.cursor/agents/docs-architect.md` | [ver](../.cursor/agents/docs-architect.md) |

### Documentos de diseño (los lee una persona o un agente al arrancar)

| Documento | Ruta | Contenido |
| :--- | :--- | :--- |
| Este archivo | `.agents/agents.md` | Capas, perfil base, modelo de amenazas, agentes, flujo |
| Diseño de skills | [`.agents/skills.md`](skills.md) | Catálogo de las 10 skills y matriz skill × agente |
| PRD y features | [`.aicontext/`](../.aicontext/PRD.md) | Especificación de producto |
| Backlog de tasks | [`.aicontext/tasks/`](../.aicontext/tasks/README.md) | Contratos de implementación `TASK-00` → `TASK-35` |

### Por qué no está todo en `.agents/`

Cursor solo descubre cada artefacto en rutas concretas, y no hay ajuste de configuración que las
redirija:

| Artefacto | Rutas soportadas | Si se mueve fuera |
| :--- | :--- | :--- |
| Rules | `.cursor/rules/*.mdc` (subcarpetas incluidas) o `AGENTS.md` | Quedan **inertes en silencio**: `alwaysApply` deja de tener efecto y no hay error |
| Subagentes | `.cursor/agents/`, `.claude/agents/`, `.codex/agents/` (+ equivalentes en `~`) | **Desaparecen**: no se pueden invocar ni delegar |
| Skills | `.agents/skills/`, `.cursor/skills/`, `.claude/skills/`, `.codex/skills/` (+ `~`) | Único caso que admitiría `.agents/`; se mantienen en `.cursor/skills/` por coherencia con las otras dos capas |

De ahí la separación: **lo ejecutable vive donde Cursor lo busca (`.cursor/`) y lo explicativo
vive en `.agents/`**, unificado por este índice. Para un proyecto cuyas rules contienen las 7
reglas inviolables de safety, una rule inerte es el peor fallo posible: dejaría de inyectarse en
cada generación de código sin que nada avise.

Consecuencia práctica: el documento de diseño de skills se llama `skills.md` y **no**
`skills/SKILL.md`, porque `.agents/skills/` es una raíz de skills que Cursor recorre y un
`SKILL.md` ahí dentro se registraría como skill real (sin frontmatter, y por tanto sin nombre ni
descripción útiles).

---

## 1. Por qué hace falta esta configuración

MetaTracer tiene un PRD con conocimiento de dominio muy preciso (regex exactas, techos de
severidad, contratos de enums, 7 reglas inviolables de safety). Sin configuración persistente:

- Cada sesión tendría que re-leer los documentos de tasks para no contradecir el PRD.
- Cualquier generación de código podría violar las reglas inviolables (p. ej. sugerir un flag
  `--insecure`, usar `httpx` crudo, o mandar el EXIF completo al LLM).

La configuración se organiza en **tres capas** según cómo se activa el conocimiento:

| Capa | Mecanismo | Cuándo aplica | Qué contiene |
| :--- | :--- | :--- | :--- |
| Rules | `.cursor/rules/*.mdc` con `alwaysApply: true` | Siempre, en toda generación de código | Lo inviolable: safety y contratos de datos |
| Skills | `.cursor/skills/<nombre>/SKILL.md` | Just-in-time, al trabajar en un módulo | Conocimiento de dominio denso por módulo |
| Subagentes | `.cursor/agents/<nombre>.md` + built-in de Cursor | Delegación de trabajo con rol y criterio | Implementación, revisión y cierre de tasks |

---

## 2. Capa 1 — Rules always-on

Estado: **creadas** (29 ago 2026).

| Rule | Archivo | Contenido |
| :--- | :--- | :--- |
| Reglas inviolables | `.cursor/rules/safety-invariants.mdc` | Las 7 reglas: red solo con `scope_confirmed`, wrapper HTTP único, cero binarios al LLM, redirects re-validados, asset fallido no tumba el run, agentes no inventan evidencia, loopback bloqueado salvo tests |
| Contratos de datos | `.cursor/rules/data-contracts.mdc` | Enums cerrados en minúsculas, `severity` NULL hasta clasificar, fórmula de `dedup_signature`, idiomas por capa (reportes/UI en inglés, docs en español), convenciones de persistencia |

Estas rules son la fuente de verdad operativa. Los skills y agentes las referencian, no las
repiten.

---

## 3. Capa 2 — Skills (just-in-time)

Cada skill encapsula el conocimiento de un módulo y se carga solo cuando se trabaja en él. El
diseño detallado de cada una está en [skills.md](skills.md).

| # | Skill | Conocimiento que encapsula | Tasks | Prioridad | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `metatracer-safety-rules` | ScopeValidator (normalización, matching, wildcard), NetworkSafetyGuard (rangos bloqueados, anti-SSRF), wrapper `safe_httpx_request` (redirects, timeouts, rate limit), confirmación de scope, logging seguro | TASK-00, transversal | Crítica | Creado |
| 2 | `metatracer-data-contracts` | Enums, ciclo de vida de un finding (detector → heurístico → agente → reporte), modelos SQLModel, dedup, repositorios, ciclo de vida del dato personal | Transversal | Crítica | Creado |
| 3 | `metatracer-supply-chain` | Lista cerrada de dependencias de TASK-00, separación runtime/dev, superficie de la imagen Docker, secretos, assets de CDN con versión fija | TASK-00, TASK-07, transversal | Crítica | Creado |
| 4 | `metadata-extraction` | EXIF/IPTC/XMP/PDF InfoDict, HTML/headers/JS (TASK-09), magic bytes, streaming con límites, sanitización de valores, dedup por hash | TASK-01, TASK-09 | Alta | Creado |
| 5 | `detector-patterns` | Las 5 regex/patrones (GPS, email, internal_path, software_version, debug_comment), niveles de confidence, anti-ruido, FindingConsolidator | TASK-02 | Alta | Creado |
| 6 | `risk-rubric` | Rúbrica de severidad, techos heurísticos (GPS máx `high`, software máx `low`, email máx `medium`), anclaje anti-alucinación, plantillas de impacto/remediación | TASK-03 (+ prompts de TASK-05) | Alta | Creado |
| 7 | `langgraph-agent-patterns` | Grafo LangGraph (nodos, estado, topología), ContextOptimizer, structured output, routing modelo fuerte/barato, fallback con tenacity, evidence guard | TASK-05 | Alta | Creado |
| 8 | `report-engine` | Ficha de finding en inglés, orden Critical→Info, exportadores Markdown/JSON/HTML, compliance notice, run vacío | TASK-04, TASK-08 | Media | Creado |
| 9 | `metatracer-ui` | Stack real de la Web UI (Next 16 + React 19 + Tailwind 4 + TanStack Query), tokens `.mt-*`, renderizado seguro sin `dangerouslySetInnerHTML`, `safeUrl`, CSP del shell y de la API, paridad CLI/UI | TASK-06, TASK-20, TASK-26, T11 | Media | Creado |
| 10 | `metatracer-testing` | Fixtures sintéticos (Pillow/pypdf/reportlab), servidor mock, bypass loopback solo-test, marcas pytest, cobertura ≥85%, Docker multi-stage | TASK-07 (+ tests de cada slice) | Media | Creado |

**Regla de adopción:** crear cada skill al abrir su slice, no antes. Los skills 1-3 ya existen
(transversales) y `metatracer-ui` (skill 9) se materializó con el cierre de TASK-26.

---

## 4. Perfil base de un agente desarrollador de MetaTracer

Todo lo de esta sección aplica a **los ocho agentes custom**, independientemente del módulo. Es
el perfil de contratación: si un agente no exhibe estos rasgos, su diff no entra. Cada archivo de
`.cursor/agents/` referencia esta sección en lugar de duplicarla.

### 4.1 Rasgos no negociables

1. **Fail-closed por defecto.** Ante duda, bloquear. Ningún camino feliz puede depender de que
   el usuario "no haga nada raro": si falta el scope, si el DNS resuelve a algo privado o si
   un campo llega vacío, la operación se aborta con una excepción del dominio, no con un
   `warning` y un `continue`.
2. **Todo input es hostil.** La metadata la escribió el target, no un usuario amable. Valores
   larguísimos, encodings roto, bytes, rutas, backticks, CRLF, HTML e incluso frases que
   parecen instrucciones para un LLM. Ningún valor de `RawMetadataItem` se concatena, se
   renderiza, se loguea ni se envía a un modelo sin pasar por sanitización y tope de tamaño.
3. **No inventa.** Ni severidades, ni CVEs, ni enums, ni campos de modelo, ni endpoints. Si no
   está en el backlog ni en el código, no existe: se pregunta (§4.4).
4. **Trazable y determinista.** Mismo input → misma salida en todo lo que no sea el LLM. Cada
   decisión queda persistida con su origen (`detector_method`, `confidence`,
   `agent_model_used`, `AgentLog`) para poder auditarla después.
5. **Falla en pequeño.** El radio de un error es un asset o un finding, nunca el run. El fallo
   se persiste con `extraction_status` / `error_message` y el pipeline continúa.
6. **Honesto al fallar.** Jamás se pone el verde debilitando una assertion, mockeando un guard
   de seguridad, silenciando un lint con `# noqa` o marcando un test como `skip`. Es preferible
   entregar menos alcance y decirlo.
7. **Explicable.** El diff se puede defender en una entrevista técnica: límites claros entre
   ingest / detect / classify / agent / report, nombres del dominio, y comentarios solo donde
   hay una decisión no evidente (nunca narrando lo que el código ya dice).
8. **Ético por diseño.** MetaTracer ayuda al programa a **borrar** metadata sensible. Ningún
   agente añade capacidades ofensivas (payloads, fuzzing, brute force, geocoding de personas)
   aunque se pidan de pasada, y ninguno documenta la herramienta como un scanner weaponizado.

### 4.2 Modelo de amenazas que todo agente lleva encima

Este es el contexto de seguridad que distingue a un agente de este proyecto de un agente
Python cualquiera. Columna **Origen**: `Spec` = exigido literalmente por una task;
`Endurecimiento` = no está escrito en el backlog, el agente lo aplica por defecto y lo
documenta en el código (regla 4 de [tasks/README.md](../.aicontext/tasks/README.md)).

| # | Amenaza | Por dónde entra | Mitigación exigida | Dueño | Origen |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | SSRF / red interna | Target del usuario, enlaces crawleados | `NetworkSafetyGuard` resuelve A+AAAA y bloquea loopback, RFC 1918, link-local (`169.254.169.254`), CGNAT, ULA, multicast **antes** del socket | pipeline | Spec |
| 2 | Redirect fuera de scope | Hops HTTP | Re-validar el host de cada hop y abortar con `RedirectOutOfScopeError` antes de leer el body; máx. 5 hops | pipeline | Spec |
| 3 | DNS rebinding / TOCTOU | Resolución entre guard y socket | Limitación aceptada del MVP: llamar la guarda inmediatamente antes de cada request y documentarlo; prohibido "arreglarlo" con hacks fuera del wrapper | safety-guardian | Spec |
| 4 | Tipo de archivo mentido | `Content-Type` y extensión | Allowlist por magic bytes para PDF/imagen (`%PDF`, `FF D8 FF`, PNG, TIFF, WEBP). HTML/JS no tienen firma fiable: se clasifican por content-type/path **después** de fallar el magic. Una URL con extensión de documento cuyo body sea HTML sigue `unsupported_type` (no reciclar error pages) | pipeline | Spec |
| 5 | Bombas de tamaño / descompresión | PDFs, imágenes, HTML y JS descargados | `MAX_FILE_BYTES` (50 MB) con aborto al primer chunk; tope de página HTML 5 MB; timeouts; límite de píxeles de Pillow y tolerancia a PDF cifrado/dañado → `failed` | pipeline | Spec + Endurecimiento |
| 6 | ReDoS en detectores | Valores de metadata arbitrarios | Regex acotadas (sin anidar cuantificadores), entrada truncada a ~2 KB, test negativo por detector | pipeline | Endurecimiento |
| 7 | Prompt injection vía metadata | Campos EXIF/XMP/HTML/JS que el target controla y viajan al LLM | El payload son **datos**, nunca instrucciones; la garantía real es el guard post-LLM (`cited_evidence` substring, `finding_type`/`evidence_snippet` inmutables, desescalado al techo), no el prompt. El body HTML/JS nunca entra al modelo | llm-agent-engineer | Spec (guard) + Endurecimiento (amenaza) |
| 8 | Fuga de secretos | Logs, `AgentLog.raw_response`, trazas de error | Nunca loguear `LLM_API_KEY`, cabeceras de auth ni el prompt completo; en `AgentLog` solo la salida estructurada | llm-agent-engineer | Spec |
| 9 | Denial of wallet | Runs con findings absurdos | 1 finding por llamada, tope ~1.500 tokens, priorización por tipo y recorte logueado | llm-agent-engineer | Spec |
| 10 | Escritura fuera de `reports/` | Slug del reporte derivado del target | Slug saneado a `[a-z0-9-]`, nombre según la nomenclatura de TASK-04, escritura confinada al directorio de salida | pipeline / ui | Spec + Endurecimiento |
| 11 | Ruptura del bloque de evidencia | Snippet con backticks o saltos de línea | Cercar el bloque de código de forma segura sin alterar los bytes de la evidencia; en la UI, escapar | pipeline / ui | Endurecimiento |
| 12 | XSS en la Web UI | Snippets y URLs del target renderizados | Prohibido `dangerouslySetInnerHTML` y markdown-a-HTML: todo dato va como nodo de texto; URLs solo por `safeUrl()` (React escapa por defecto) | v2-ui-engineer | Endurecimiento |
| 13 | Log injection | Valores de metadata con CRLF | Formato fijado en la skill `metatracer-safety-rules`: nunca interpolar crudo un valor del target; sustituir `\r`/`\n` y truncar a ~150 chars; contexto como campo estructurado | pipeline (dueño del formato), revisado por safety-guardian | Endurecimiento |
| 14 | Datos personales (GPS, emails, nombres) | Es el producto, pero también un riesgo | Ciclo de vida fijado en la skill `metatracer-data-contracts`: minimización en origen, `value` siempre texto, DB y reportes en `.gitignore` y fuera de la imagen, sin envío a terceros, snippet (no campo completo) al LLM | pipeline (persistencia), revisado por safety-guardian | Spec |
| 15 | Cadena de suministro | Dependencias nuevas, imagen Docker, assets de CDN | Lista cerrada en TASK-00 sincronizada con `pyproject.toml`; dev nunca importado desde `src/`; sin instalar código en runtime; imagen no-root sin compiladores; CDN con versión fija. Documentado en la skill `metatracer-supply-chain` | pipeline (deps) / test (imagen) / ui (CDN), con veto de `safety-guardian` | Spec + Endurecimiento |

### 4.3 Definition of Ready / Definition of Done

Un agente **no empieza** hasta que: la task existe en `.aicontext/tasks/`, sus dependencias
están cerradas, la skill de su módulo existe, y puede citar el DoD que va a cumplir.

Un cambio **está done** cuando: los checkboxes de la task están verdes, `ruff` pasa sobre
`src/` y `tests/`, los tests mínimos de esa task existen y pasan, `safety-guardian` no reporta
bloqueantes, no hay nada de slices posteriores, y si se tomó una decisión no especificada queda
documentada en el código.

### 4.4 Protocolo de escalado: cuándo parar y preguntar

| Situación | Qué hace el agente |
| :--- | :--- |
| Cumplir la petición exigiría violar una regla inviolable | **Para siempre.** Explica el conflicto y propone la alternativa segura |
| Falta un contrato (enum, campo, endpoint) o dos documentos se contradicen | **Para.** No inventa el valor: primero se actualiza `tasks/README.md` |
| Hace falta una dependencia o variable de entorno nueva | **Para.** Necesita justificación explícita y revisión de safety |
| Decisión de producto o legal ambigua (wording del aviso, UX de confirmación) | **Para.** Es del humano |
| Detalle de implementación no especificado | **No para.** Elige la opción más simple que respete las reglas y la documenta en un docstring |

### 4.5 Anti-patrones que descalifican un cambio

Señales de que un agente se está desviando, sin importar quién sea:

- Usar `httpx` (o `requests`, o `urllib`) directamente "solo para probar".
- Introducir cualquier interruptor que relaje el safety: `--insecure`, `verify=False`,
  `ALLOW_LOOPBACK` fuera del proceso de test, `follow_redirects=True` sin re-validación.
- Mockear, parchear o rodear un control de seguridad para que un test pase.
- Rellenar `severity` en un detector, o dejar prosa de plantilla como si fuera análisis del LLM.
- Mandar "un poco más de contexto" al modelo: EXIF completo, HTML, thumbnails, bytes.
- Ampliar el alcance por iniciativa propia (React en TASK-00, LLM en TASK-02, auth en TASK-06).
- Cambiar un documento de `.aicontext/` para que cuadre con el código en lugar de al revés.

---

## 5. Capa 3 — Subagentes

### 5.1 Agentes custom (creados)

Un archivo por agente en `.cursor/agents/`. Cada archivo es el system prompt del subagente:
frontmatter con `name` / `description` / `model` (+ `readonly` donde aplica) y un cuerpo con
contexto a cargar, procedimiento, reglas de construcción, límites, criterio de éxito y
anti-patrones propios.

| Agente | Archivo | Misión en una línea | Tasks | `readonly` |
| :--- | :--- | :--- | :--- | :--- |
| `safety-guardian` | [safety-guardian.md](../.cursor/agents/safety-guardian.md) | Revisa diffs contra las 7 reglas inviolables y el modelo de amenazas; único con derecho de veto | Transversal | Sí |
| `pipeline-engineer` | [pipeline-engineer.md](../.cursor/agents/pipeline-engineer.md) | Núcleo determinista: safety core, persistencia, extracción, detección, heurístico y reportes | 00 → 04, 09 | No |
| `llm-agent-engineer` | [llm-agent-engineer.md](../.cursor/agents/llm-agent-engineer.md) | Grafo LangGraph, prompts versionados, validador post-LLM y fallback heurístico | 05 | No |
| `ui-engineer` | [ui-engineer.md](../.cursor/agents/ui-engineer.md) | CLI, API y Web UI sobre un único `ScanOrchestratorService` | 06, 08, 20, 25 (UI), 26 | No |
| `ui-architect` | [ui-architect.md](../.cursor/agents/ui-architect.md) | Arquitecto de UI/UX: analiza la UI y produce contratos de diseño (`.aicontext/ui/`) para `ui-engineer`, sin tocar implementación | 26 (contrato) | Sí |
| `v2-ui-engineer` | [v2-ui-engineer.md](../.cursor/agents/v2-ui-engineer.md) | Retoque visual de Web V2 solo en `web/`. No sustituye a `ui-engineer` | R1–R6 de `v2-ui-refresh.md` | No |
| `test-engineer` | [test-engineer.md](../.cursor/agents/test-engineer.md) | Fixtures sintéticos, mock local, e2e, cobertura y Docker | 07 + DoD de cada task | No |
| `docs-architect` | [docs-architect.md](../.cursor/agents/docs-architect.md) | Explicabilidad: README, ADRs, walkthrough y coherencia `.aicontext` ↔ código | Cierre de slice | No |

**Invocación.** Cursor delega automáticamente según la `description`, y también se pueden llamar
de forma explícita (`/safety-guardian revisa el diff del crawler`). `safety-guardian` y
`ui-architect` van en `readonly` a propósito: revisan y producen especificaciones, no editan.

**Por qué `pipeline-engineer` también cubre TASK-03:** el clasificador heurístico es código
determinista sin red ni LLM (rúbrica, techos, plantillas). `llm-agent-engineer` empieza en
TASK-05, cuando entra el modelo.

**Por qué existe `ui-architect`:** el rediseño de la Web UI (TASK-26) es una decisión de producto
con superficie HIGH RISK (modal de scope, SSE, drawer). `ui-architect` separa el diseño visual de
la implementación: analiza la UI actual y emite contratos (`.aicontext/ui/` — `ui-architecture.md`,
`design-system.md`, `component-map.md`, `redesign-plan.md`) que `ui-engineer` implementa sin
decidir arquitectura de UI sobre la marcha. Su archivo está marcado `readonly` y la orden de
parada del rediseño exige que nada de esa fase toque `.cursor/agents/ui-architect.md`.

### 5.2 Propiedad de módulos

Quién escribe dónde, para que dos agentes no se pisen y para saber a quién reclamar.

| Ruta | Dueño | Revisión obligatoria |
| :--- | :--- | :--- |
| `src/metatracer/core/` | pipeline-engineer | safety-guardian (siempre) |
| `src/metatracer/db/` | pipeline-engineer | safety-guardian (contratos) |
| `src/metatracer/extractors/` | pipeline-engineer | safety-guardian |
| `src/metatracer/detectors/` | pipeline-engineer | — |
| `src/metatracer/reports/` | pipeline-engineer | ui-engineer (consumidor) |
| `src/metatracer/agents/` | llm-agent-engineer | safety-guardian |
| `src/metatracer/services/`, `api/`, `cli/` | ui-engineer | safety-guardian (API) |
| `.aicontext/ui/` (contratos de diseño) | ui-architect | v2-ui-engineer (consumidor) |
| `web/` (la Web UI: Next.js) | v2-ui-engineer | safety-guardian si hay CSP, scope o dependencia |
| `tests/`, fixtures | test-engineer | safety-guardian (bypass loopback) |
| `pyproject.toml` | pipeline-engineer | safety-guardian (lista cerrada de dependencias) |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | test-engineer | safety-guardian (superficie de la imagen) |
| `.env.example`, `.gitignore` | pipeline-engineer | safety-guardian (secretos y flags) |
| `.aicontext/`, `.agents/`, README | docs-architect | humano |

Los tests de una slice los escribe el agente que implementa esa slice; `test-engineer`
consolida, no rescata.

### 5.3 Agentes built-in de Cursor (aprovechar)

| Agente | Uso en MetaTracer |
| :--- | :--- |
| `explore` | Consultas al PRD/backlog ("¿qué dice TASK-03 sobre techos de GPS?") sin ensuciar el contexto principal |
| `bugbot` | Revisión de lógica en cada PR de slice |
| `security-review` | Revisión de superficie de seguridad (SSRF, sanitización, manejo de binarios) antes de mergear |
| `ci-investigator` | Diagnóstico de checks fallidos si se añade GitHub Actions (opcional en MVP) |

`security-review` **no sustituye** a `safety-guardian`: el built-in busca vulnerabilidades
genéricas; el custom verifica las 7 reglas específicas de este producto.

---

## 6. Flujo de trabajo y handoffs

```text
1. explore                 consulta la spec si hay dudas
2. ui-architect            (solo rediseños de UI) analiza y emite contratos en .aicontext/ui/
3. <engineer del slice>    implementa la task + sus tests
4. safety-guardian         revisa el diff        →  bloqueante = no avanza
5. test-engineer           consolida DoD / fixtures
6. bugbot + security-review en el PR             →  merge
7. docs-architect          cierra el slice (README / ADR / walkthrough)
```

Reglas de orquestación:

- Las tasks se implementan **en orden numérico**; las dependencias no son opcionales.
- Un agente no adelanta trabajo de slices posteriores (nada de React en TASK-00, nada de LLM en
  TASK-02).
- Cada subagente arranca con **contexto limpio**: no hereda la conversación anterior. Por eso su
  archivo enumera qué debe cargar, y por eso el handoff entre agentes es un **contrato de datos**
  (modelos y estados persistidos), no una conversación.
- Si una decisión no está en la task ni en la feature, se elige la opción más simple que respete
  las reglas inviolables y se documenta en código (§4.4).
- `safety-guardian` es el único cuyo veredicto bloquea; el resto de revisiones informan.

---

## 7. Plan de adopción

| Fase | Slice | Acción |
| :--- | :--- | :--- |
| 0 — Pre-código | — | Rules always-on + skills `metatracer-safety-rules` y `metatracer-data-contracts` + los 6 subagentes en `.cursor/agents/` (hecho) |
| 1 — Pipeline determinista | 1-2 | Crear skills `metadata-extraction` y `detector-patterns`; trabajar con `pipeline-engineer` y `safety-guardian` |
| 2 — IA e interfaces | 3-4 | Crear skills `risk-rubric`, `langgraph-agent-patterns`, `report-engine`, `metatracer-ui`; entran `llm-agent-engineer` y `ui-engineer` |
| 3 — Cierre MVP | 5 | Crear skill `metatracer-testing`; entran `test-engineer` y `docs-architect`; activar `bugbot`/`security-review` en PRs |
| 4 — Post-MVP | 6-7 | TASK-08 (v1.1) y TASK-09 (v1.2) **cerradas**. Reusan skills de módulo; materializar las skills 4-8 y 10 sigue pendiente |
| 5 — Plataforma | 8+ | TASK-10 → TASK-26 (v2.0 → v3.1) **cerradas**. Entra `ui-architect` para el rediseño de UI (TASK-26); se materializan los skills del módulo al abrir su task |

Los subagentes ya existen (8 desde la incorporación de `v2-ui-engineer`), pero **las skills siguen
creándose al abrir su slice**: el agente sin su skill funciona con las rules y su propio prompt;
con la skill, además conoce los valores exactos del módulo. `metatracer-ui` es la primera skill
de módulo materializada (cubre el design system de TASK-26).
