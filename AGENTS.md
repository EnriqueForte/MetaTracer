# MetaTracer — instrucciones para agentes

Herramienta de descubrimiento de metadata sensible para bug bounty y red team
**autorizados**. Escanea assets públicos de targets que no controlamos, guarda
datos personales (GPS, emails) y pasa texto escrito por el target a un LLM.

Este archivo es el **punto de entrada** para cualquier agente. No duplica las
reglas: apunta a ellas.

## Lo inviolable (léelo antes de tocar código)

Dos rules se aplican siempre, sin excepción:

- `.cursor/rules/safety-invariants.mdc` — las 7 reglas (red solo con scope
  confirmado y por el wrapper único, cero binarios, redirects in-scope, un asset
  fallido no tumba el run, los agentes no inventan evidencia, loopback bloqueado).
- `.cursor/rules/data-contracts.mdc` — enums cerrados en minúsculas, `severity`
  NULL hasta clasificar, `dedup_signature`, idiomas por capa.

Si una petición exige violarlas, **para** y explica el conflicto.

## Mapa del repositorio

| Ruta | Qué es |
| :--- | :--- |
| `src/metatracer/core/` | Configuración, logging, safety core (`safety/scope.py`, `guard.py`, `http.py`) |
| `src/metatracer/extractors/` | Ingesta, crawler, allowlist por magic bytes, PDF/imagen/HTML/JS/headers |
| `src/metatracer/detectors/` | Los 5 detectores deterministas (sin severity) |
| `src/metatracer/classification/` | Rúbrica y clasificador heurístico |
| `src/metatracer/agents/` | Grafo LangGraph, guard post-LLM, fallback |
| `src/metatracer/reports/` | Exportadores Markdown/JSON/HTML/CSV/Bounty |
| `src/metatracer/services/`, `cli/`, `api/` | Orquestador único, CLI Typer, **API FastAPI (solo-API)** |
| `web/` | **La Web UI** (Next.js 16 + React 19 + Tailwind 4). Servida desde la raíz |
| `deploy/` | `Caddyfile` (un solo origen: `/api` → FastAPI, resto → Next) |
| `tests/` | `unit/`, `agents/`, `integration/` (+ e2e). Ver `tests/README.md` |
| `.aicontext/` | PRD, features, backlog (`tasks/`), ADR (`decisions/`), arquitectura |
| `.agents/agents.md` | Catálogo de subagentes y modelo de amenazas (§4.2) |

**Web V1 (Jinja + Alpine) se retiró en T11** (ADR-0016). Si encuentras referencias
a plantillas, Alpine o `/static` de V1 en código, es deuda: no la reintroduzcas.

## Comandos

```bash
# Python (desde la raíz; el venv está en .venv)
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m pytest -m "not e2e"      # loop rápido
.venv/Scripts/python.exe -m pytest                    # suite completa

# Web (desde web/)
npm test          # Vitest + contratos de routing/proxy
npm run build     # incluye typecheck
npm run test:e2e  # Playwright (requiere build previo)
```

El DoD de cualquier cambio: `ruff` limpio, los tests de la slice verdes,
cobertura ≥ 85% en `core`/`detectors`/`extractors`/`reports`, y
`git diff` sin nada fuera de alcance.

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
- **Idiomas:** reportes y UI en inglés; documentación en español.

## Skills y subagentes

- Skills (just-in-time): `.cursor/skills/` — 10 materializadas, catálogo en
  `.agents/skills.md`.
- Subagentes: `.cursor/agents/` — `safety-guardian` (veto), `pipeline-engineer`,
  `llm-agent-engineer`, `ui-engineer` (CLI+API), `v2-ui-engineer` (Web UI),
  `test-engineer`, `docs-architect`, `ui-architect` (obsoleto para V2).

`safety-guardian` es el único cuyo veredicto **bloquea** un merge.

## Cuándo parar y preguntar

- Cumplir la petición exigiría violar una regla inviolable.
- Falta un contrato (enum, campo, endpoint) o dos documentos se contradicen.
- Hace falta una dependencia o variable de entorno nueva.
- La decisión es de producto o legal (wording del aviso, UX de confirmación).
- Necesitas un secreto o acceso externo.

Detalle de implementación no especificado: elige la opción más simple que respete
las reglas y documéntala en el código.
