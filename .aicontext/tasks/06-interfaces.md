# TASK-06: Interfaces de Usuario (CLI y Web UI)

**Módulo:** Interfaces de Usuario  
**Referencia PRD:** [Interfaces](../features/06-interfaces.md)  
**Dependencias:** [TASK-00](00-architecture-and-safety.md) … [TASK-05](05-ai-agents.md)  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Dos superficies sobre **un** `ScanOrchestratorService`: CLI (Typer + Rich) y Web UI local. Paridad de negocio: mismo pipeline, mismos findings para el mismo input.

Stack de UI del MVP (decisión cerrada para no abrir un segundo runtime): **FastAPI + Jinja2 + Tailwind (CDN) + Alpine.js**, tema oscuro. Sin Node/React en v1.0. Si más adelante se quiere SPA, se sustituye el front; la API no cambia.

---

## 2. Subtareas Detalladas

### Subtarea 6.1: `ScanOrchestratorService`

Secuencia fija:

1. Exigir `scope_confirmed` (TASK-00).
2. Crear `Run` (`pending` → `running`).
3. Descubrir y descargar (TASK-01).
4. Extraer metadata (TASK-01).
5. Detectores (TASK-02).
6. Clasificador heurístico (TASK-03).
7. Grafo LangGraph (TASK-05) — fallback incluido.
8. Construir reporte (TASK-04) y devolver paths de export.
9. `Run.status = completed` o `failed` / `aborted`. Actualizar contadores.

Un asset que falla no aborta el run. Excepciones de safety (`ScopeNotConfirmedError`, `SecurityViolationError`) sí abortan con mensaje claro.

**Concurrencia:** un scan activo por proceso. SQLite no se usa como cola multi-writer. `POST /api/runs` rechaza con 409 si ya hay un run `running`.

**Progreso:**

```python
class ProgressStage(str, Enum):
    scope_validation = "scope_validation"
    discovery = "discovery"
    downloading = "downloading"
    extraction = "extraction"
    detection = "detection"
    ai_analysis = "ai_analysis"
    report_generation = "report_generation"
    completed = "completed"
    failed = "failed"

class ProgressEvent(BaseModel):
    run_id: str
    stage: ProgressStage
    current_step: int
    total_steps: int
    message: str
    current_asset: str | None = None
```

CLI y SSE consumen el mismo callback/cola asyncio.

---

### Subtarea 6.2: CLI (Typer + Rich)

```text
metatracer scan [TARGETS]...
    -s, --scope-domain TEXT     repetible; dominios autorizados (obligatorio)
    -y, --confirm-scope         confirma autorización (CI/scripts)
    -d, --depth                 brief|standard|detailed  [standard]
    -o, --output-dir            [./reports]
    -f, --format                md|json|all  [all]

metatracer report RUN_ID        re-exporta un run ya persistido
metatracer list-runs            tabla mínima: id, target, status, counts, fecha
                                (historial local; el dashboard de plataforma es v2.0)
```

El scope **nunca** se infiere en silencio a partir del target. Si `-s` falta, error o prompt. Sin `-y`, prompt: `Do you confirm explicit authorization to audit this target? [y/N]` (default N).

UX:

- Banner + aviso ético.
- Spinners / progress bar por etapa.
- Tabla final coloreada: critical rojo bold, high magenta, medium yellow, low cyan, info dim.
- Exit `0` si el run termina (aunque haya 0 findings). Exit `1` si error fatal de safety/config/orquestación.

---

### Subtarea 6.3: API FastAPI

Bind default `127.0.0.1:8000`. En Docker, `BIND_HOST=0.0.0.0` (TASK-07). Sin autenticación en el MVP: documentar “solo localhost / red de confianza”.

| Método | Ruta | Contrato |
| :--- | :--- | :--- |
| `POST` | `/api/runs` | Body JSON: `{ "targets": [...], "scope_domains": [...], "scope_confirmed": true, "reasoning_depth": "standard" }`. Si `scope_confirmed` no es true → 403. 409 si hay run running. Respuesta `{ "run_id": "..." }` 202. |
| `GET` | `/api/runs/{run_id}` | Status, contadores, error_message |
| `GET` | `/api/runs/{run_id}/stream` | **SSE** (`text/event-stream`) de `ProgressEvent`. No WebSocket en el MVP. |
| `GET` | `/api/runs/{run_id}/findings` | Lista ordenada; query opcional `severity=` |
| `GET` | `/api/runs/{run_id}/export?format=md\|json` | Attachment |

Páginas HTML: `GET /` wizard de scan, `GET /runs/{run_id}` resultados. Estáticos bajo `/static`.

---

### Subtarea 6.4: Web UI

- Modal **bloqueante** de confirmación de scope (checkbox + botón). Sin check, el POST no sale.
- Form: textarea de targets (uno por línea), input de scope domains, select de depth, start.
- Progreso en vivo vía EventSource.
- Dashboard: badges de conteo (filtran la tabla), tabla ordenada por severidad, drawer con evidence + copy, justificación, impacto, repro, remediación.
- Botones `Download Markdown` / `Download JSON`.
- Estado vacío: mensaje de cero hallazgos, no spinner eterno ni error.
- Errores por asset visibles en log corto; no pantallazo blanco.

Tema oscuro táctico, layout limpio nivel portfolio, **un flujo**: nuevo run → progreso → resultados → export. Sin gestión de usuarios ni dashboard multi-run elaborado (v2.0). `list-runs` es solo CLI en esta task; el historial UI es [TASK-08](08-usability.md).

---

## 3. Fuera de alcance de esta tarea

- React/Vue/Vite, auth, SaaS, notificaciones, dashboard de plataforma (v2.0).
- Filtros avanzados e historial UI — cubierto por [TASK-08](08-usability.md) (v1.1, completada).
- Cancelación cooperativa de un run (nice-to-have; si sale barato, `aborted` ya existe en el enum).
- Flag `--insecure` / desactivar safety.

---

## 4. Tests mínimos

- `tests/unit/test_orchestrator_scope.py` — sin confirmación no hay HTTP.
- `tests/integration/test_cli_scan_help.py` — `metatracer scan --help` y rechazo sin `-y` en entorno no TTY (exit ≠ 0).
- `tests/integration/test_api_scope.py` — `POST` con `scope_confirmed: false` → 403.

El e2e feliz con fixtures es TASK-07.

---

## 5. Criterios de Aceptación (DoD)

- [x] `metatracer scan target.com -s target.com -y` produce Markdown bajo `./reports`.
- [x] Web UI en `http://127.0.0.1:8000`: modal de scope → scan → progreso SSE → resultados.
- [x] CLI y UI muestran los mismos findings/severities para el mismo run_id.
- [x] Sin confirmación de scope, no arranca el scan.
- [x] Cero hallazgos → resumen claro, exit 0 / página válida.
- [x] Segundo `POST /api/runs` con uno running → 409.
