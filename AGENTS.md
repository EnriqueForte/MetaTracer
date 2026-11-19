# MetaTracer — instrucciones para agentes

Herramienta de descubrimiento de metadata sensible para bug bounty y red team
**autorizados**. Escanea assets públicos de targets que no controlamos, guarda
datos personales (GPS, emails) y pasa texto escrito por el target a un LLM.

Este archivo es el **punto de entrada** para cualquier agente. No duplica las
reglas: apunta a ellas.

**Antes de código:** [`MEMORY.md`](MEMORY.md) (qué está abierto) y
[`specs/README.md`](specs/README.md) (ritual SDD). TASK-00–53 están cerradas.
Spec 56 (instalador/lanzador) está **closed**.

## Lo inviolable (léelo antes de tocar código)

Dos rules se aplican siempre, sin excepción:

- `.cursor/rules/safety-invariants.mdc` — las 7 reglas (red solo con scope
  confirmado y por el wrapper único, cero binarios, redirects in-scope, un asset
  fallido no tumba el run, los agentes no inventan evidencia, loopback bloqueado).
- `.cursor/rules/data-contracts.mdc` — enums cerrados en minúsculas, `severity`
  NULL hasta clasificar, `dedup_signature`, idiomas por capa. Specs 36–53 closed.
  Overlay v3.4 sin reserved. Spec 56 clone/install **closed**. `secret` es
  `finding_type` (TASK-49). Findings
  `internal_endpoint`/`cloud_storage` y namespaces `ooxml`/`odf` están en TASK-37.

Si una petición exigiría violarlas, **para** y explica el conflicto.

## Mapa del repositorio

| Ruta | Qué es |
| :--- | :--- |
| `MEMORY.md` | Memoria de trabajo (versión, specs, prohibiciones) |
| `specs/` | Overlay SDD: specs activas y reserved |
| `src/metatracer/core/` | Configuración, logging, safety core (`safety/scope.py`, `guard.py`, `http.py`) |
| `src/metatracer/extractors/` | Ingesta, crawler, allowlist por magic bytes, PDF/imagen/HTML/JS/headers/office |
| `src/metatracer/detectors/` | Detectores deterministas (sin severity), incl. `network.py` |
| `src/metatracer/classification/` | Rúbrica y clasificador heurístico |
| `src/metatracer/agents/` | Grafo LangGraph, guard post-LLM, fallback |
| `src/metatracer/reports/` | Exportadores Markdown/JSON/HTML/CSV/Bounty |
| `src/metatracer/services/`, `cli/`, `api/` | Orquestador único, CLI Typer, **API FastAPI (solo-API)** |
| `web/` | **La Web UI** (Next.js 16 + React 19 + Tailwind 4). Servida desde la raíz |
| `lab/puertomontevideo/` | Target sintético (spec 53). No es producto. Preview local. |
| `deploy/` | `Caddyfile` (un solo origen: `/api` → FastAPI, resto → Next) |
| `install.cmd` / `install.sh` | Instalador post-clone (Windows / Linux-Parrot). Spec 56. |
| `MetaTracer.cmd` / `run.sh` | Lanzador de la app (API + Web UI). Spec 56. |
| `tests/` | `unit/`, `agents/`, `integration/` (+ e2e). Ver `tests/README.md` |
| `.aicontext/` | PRD, features, backlog cerrado (`tasks/` 00–53), ADR, arquitectura |
| `.aicontext/ui/design-system-v2.md` | **Contrato visual vigente** (tokens `--mt-*`, densidad, panel, procedencia) |
| `.agents/agents.md` | Catálogo de subagentes y modelo de amenazas (§4.2) |

**Web V1 (Jinja + Alpine) se retiró en T11** (ADR-0016). Si encuentras referencias
a plantillas, Alpine o `/static` de V1 en código, es deuda: no la reintroduzcas. Los
documentos `.aicontext/ui/{design-system,ui-architecture,component-map,redesign-plan}.md`
describen esa V1 y están marcados como históricos: no son contrato.

## Comandos

```bash
# Clone → instalador → app (Windows / Linux-Parrot)
./install.sh && ./run.sh          # Linux
.\install.cmd ; .\MetaTracer.cmd  # Windows

# Python (desde la raíz; el venv está en .venv)
.venv/Scripts/python.exe -m ruff check src tests scripts
.venv/Scripts/python.exe -m pytest -m "not e2e"      # loop rápido
.venv/Scripts/python.exe -m pytest                    # suite completa

# Web (desde web/)
npm test          # Vitest + contratos de routing/proxy
npm run build     # incluye typecheck
npm run test:e2e  # Playwright (requiere build previo)
```

El DoD de cualquier cambio: `ruff` limpio, los tests de la slice verdes,
cobertura ≥ 85% en `core`/`detectors`/`extractors`/`reports`, y
`git diff` sin nada fuera de alcance. Código de producto exige spec `active` + task.

## Convenciones que no se negocian

- **Un solo frontend.** La UI es `web/` (Next). No añadas plantillas server-side.
- **Un solo origen.** Cookies `SameSite=Lax` y CSP `connect-src 'self'`: no
  introduzcas CORS ni un segundo host.
- **La autoridad es el servidor.** La UI refleja estados; ocultar un control no
  sustituye al 403.
- **Renderizado como texto.** Prohibido `dangerouslySetInnerHTML` y
  markdown-a-HTML; URLs solo por `safeUrl()`.
- **Lista cerrada de dependencias.** Añadir una exige justificación y revisión
  de supply chain; `pyproject.toml` y `requirements.in` deben ir en lockstep.
- **Idiomas:** reportes exportados y CLI en inglés; Web UI en español; documentación en español.
- **SDD:** spec reserved ≠ permiso para implementar. Skill `metatracer-sdd`.

## Skills y subagentes

- Skills (just-in-time): `.cursor/skills/` — 13 materializadas (incluye
  `metatracer-investigations`), catálogo en `.agents/skills.md`.
- Subagentes: `.cursor/agents/` — `safety-guardian` (veto), `pipeline-engineer`,
  `llm-agent-engineer`, `ui-engineer` (CLI+API), `v2-ui-engineer` (Web UI, único
  dueño del navegador), `ui-architect` (V2, readonly, contratos visuales),
  `test-engineer`, `docs-architect` (`MEMORY.md` + `specs/`).

`safety-guardian` es el único cuyo veredicto **bloquea** un merge.

## Cuándo parar y preguntar

- Cumplir la petición exigiría violar una regla inviolable.
- Falta un contrato (enum, campo, endpoint) o dos documentos se contradicen.
- Spec `reserved` o no hay TASK-NN y piden código de esa slice.
- Hace falta una dependencia o variable de entorno nueva.
- La decisión es de producto o legal (wording del aviso, UX de confirmación).
- Necesitas un secreto o acceso externo.

Detalle de implementación no especificado: elige la opción más simple que respete
las reglas y documéntala en el código.
