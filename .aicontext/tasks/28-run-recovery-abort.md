# TASK-28: Recuperación de runs huérfanos y abort cooperativo (v3.2)

**Módulo:** `services/orchestrator.py`, `api/runs.py`, `cli/main.py`, Web V2
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P1-1
**Dependencias:** TASK-27
**Estado:** **Cerrada** (2026-10-03). ruff limpio; cobertura core/detectors/extractors/reports **90.78%** (710 passed, not e2e). Vitest de la Web V2 en verde, incluido el botón Abort.

Al arrancar, los runs `pending`/`running` con `started_at` anterior al proceso quedan `aborted` (`error_message="interrupted: process restarted"`, `completed_at` UTC) y disparan notificación y webhook `aborted`. `POST /api/runs/{id}/abort`, Ctrl+C en `scan`/`watch` y el botón de la Web V2 cancelan el scan en curso. El SSE terminal es `aborted`, distinto de `failed`.

Limitación multi-proceso: los slots de concurrencia viven en memoria. Un segundo proceso solo aborta runs empezados antes de su arranque; no es un lock entre procesos.

---

## 1. Objetivo técnico

Hoy un reinicio del servidor deja los runs en `running` para siempre (`orchestrator.py` ~L386–396, documentado como "fuera del MVP") y no existe forma de detener un scan. La UI muestra scans eternos y el slot de concurrencia solo se libera al terminar.

## 2. Subtareas

### 28.1 Recovery al arrancar

- En el lifespan de la API y al inicio de `scan`/`watch` en la CLI: marcar como `aborted` todo run en `pending`/`running` que no pertenezca a este proceso, con `error_message="interrupted: process restarted"` y `finished_at` UTC.
- Con `METATRACER_MAX_CONCURRENT_RUNS>1` y PostgreSQL compartido por varios procesos, la recuperación debe ser segura: solo runs con `started_at` anterior al arranque del proceso actual (documentar la limitación multi-proceso).
- Emitir notificación y evento de webhook `aborted` como en un abort normal.

### 28.2 Abort cooperativo

- `ScanOrchestratorService.abort(run_id)`: cancela la `asyncio.Task` del run; `_execute_pipeline` captura `CancelledError`, persiste `aborted`, publica el evento terminal en `ProgressBus` y libera el slot.
- Los assets en curso se marcan `skipped`/`failed` según corresponda; no se exportan reportes parciales salvo que ya existan.
- `shutdown()`: tras cancelar, persistir `aborted` (en vez de dejar `running`).

### 28.3 Superficies

- API: `POST /api/runs/{id}/abort` (operator + CSRF). 404 si no existe, 409 si ya es terminal.
- CLI: Ctrl+C durante `scan` persiste `aborted` limpiamente.
- Web V2: botón "Abort scan" en `run-progress.tsx` con confirmación (usar `ui/dialog.tsx`), oculto para viewers.

## 3. Fuera de alcance

- Reanudar un run abortado.
- Cola de scans pendientes.

## 4. Tests mínimos

- Run `running` en BD + arranque de la app → queda `aborted` con `error_message`.
- `POST /abort` sobre run activo → SSE emite terminal `aborted`, slot liberado, un nuevo scan arranca sin 409.
- `POST /abort` sobre run `completed` → 409; viewer → 403; sin CSRF → 403.
- `shutdown()` deja los runs en `aborted`.
- Test de UI: botón visible solo para operator y solo con run activo.

## 5. Criterios de aceptación (DoD)

- [x] Ningún run queda en `running` tras un reinicio.
- [x] Abort disponible en API, CLI (Ctrl+C) y Web V2.
- [x] `aborted` ≠ `failed` en todas las superficies (contrato TASK-20).
- [x] Suite verde + ruff limpio + cobertura ≥85%.
