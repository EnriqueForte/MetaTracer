# TASK-22: Modo watch / headless con notificación de deltas (v3.0, Eje A)

**Módulo:** Plataforma v3.0 — operación continua (fuente: `features/12-platform-v3.md`, Eje A)
**Referencia PRD:** [Interfaces](../features/06-interfaces.md), [Historial](08-usability.md), [Webhooks](../tasks/15-webhooks.md)
**Dependencias:** TASK-00 … TASK-21 (todo el backlog previo)
**Estado:** **Cerrada 2026-09-16.** Implementada, testeada y cerrada el mismo día.

---

## 1. Objetivo técnico

Un engagement real no es un scan puntual: es redescubrir, reapuntar y reportar en el tiempo. Hoy `metatracer scan` corre el pipeline una vez y termina; la plataforma v3.0 necesita un **modo headless continuo** que re-escane un scope con cadencia configurable y solo notifique **deltas** (findings nuevos que no existían en ningún run previo con el mismo `(scope, asset, dedup_signature)`).

Principios (heredados de la visión v3.0 y del pipeline):

- **Reutiliza `ScanOrchestratorService` tal cual** — mismo pipeline, mismo safety, mismo lock por run. El watch no toca las 7 reglas inviolables: cada scan pasa por el gate de scope.
- **El delta es determinista y sin LLM**: la "memoria" es la base local; un run nuevo compara su set de `dedup_signature` contra los runs anteriores del mismo scope.
- **Cero dependencias nuevas**: el programador es un bucle `asyncio.sleep` con `--interval`; el cron real (`--cron`) queda explícitamente como mejora futura (requeriría aprobación de supply-chain para `apscheduler`).
- **La notificación reutiliza TASK-15**: los webhooks ya tienen retries, relay buffer y anti-SSRF. Solo se añade un campo `new_findings` a `PAYLOAD_KEYS` (payload plano, mismo contrato).
- **Operación robusta**: un solo watch por scope (lock de archivo), backoff doble tras N scans fallidos (reusando el posture de backoff de webhooks), no reintentos en bucle descontrolado.

## 2. Subtareas

### 22.1 Comando `metatracer watch` — ✅

Implementado en `cli/main.py`:

- `--scope <id>`: el scope guardado a re-escaniar (obligatorio; única fuente de scope — nunca inferido).
- `--interval <seconds>`: cadencia del bucle (default 6h = 21600s).
- `--once`: correr una sola iteración y salir (para CI/smoke).
- `--webhook <id>`: opcional; resuelve un `WebhookDispatcher` (igual que el lifespan de la API, mismo anti-SSRF guard) y notifica los terminal events con `new_findings`.
- El comando vive en `_execute_watch` → `_watch_loop` → `_watch_iteration` (un solo `asyncio.run`, como `_execute_scan`) y construye un `ScanRequest` con `watch=True`.
- Lock por scope: molinete en temp (`fcntl.flock` en POSIX, `os.open(O_CREAT|O_EXCL)` en Windows) — un segundo `watch` sobre el mismo scope falla limpio.
- El loop: `await asyncio.sleep(interval)` con backoff doble (`min(max_backoff, base * 2**consecutive_failures)`) tras fallos consecutivos.

### 22.2 Delta de findings (determinista) — ✅

`services/watch.py` (nuevo): `DeltaResult` + `DeltaReporter`:

- `compute_delta(run_id) -> DeltaResult`: carga los `dedup_signature` del run actual y los compara con el set histórico del mismo `allowed_scope` snapshot (todos los runs previos con el mismo snapshot, vía `RunRepository.list_recent(limit=None)`).
- El cálculo es local (cero red, cero LLM), determinista (set de signatures), y respeta el contrato de datos (`dedup_signature` ya está indexado y es estable).
- Integración: `ScanRequest.watch: bool = False` + `ScanOrchestratorService(delta_reporter=...)`. En `_notify_run_finished`, si `_active_watch` y hay reporter, se computa el delta y `new_findings` viaja en el webhook; un fallo degrada a `0`.

### 22.3 Webhook con `new_findings` — ✅

- `api/webhooks.py`: `"new_findings"` añadido a `PAYLOAD_KEYS` (siempre presente, default 0 — el contrato sigue plano y cerrado).
- `WebhookDispatcher.enqueue_terminal(..., new_findings: int = 0)` → `_build_payload` incluye `new_findings: max(new_findings, 0)`.

### 22.4 Tests mínimos — ✅

- `tests/unit/test_watch_delta.py`: delta del primer run (todo nuevo), run repetido (0), mezcla (solo los genuinamente nuevos), scope aislado, run inexistente.
- `tests/unit/test_watch_cli.py`: help (once/interval), `--once` con scope inexistente aborta, lock por scope rechaza un segundo watcher.
- `tests/unit/test_watch_orchestrator.py`: el terminal event de un watch lleva `new_findings` (vía `DeltaReporter` real + webhook fake); un run no-watch reporta 0; un watch repetido reporta 0.
- `tests/unit/test_webhook_dispatcher.py`: `new_findings` default 0 y viaje del contador en el payload (`set(payload) == set(PAYLOAD_KEYS)`).

---

## 3. Fuera de alcance (v3.0, Eje A)

- Cron real (`--cron`) — requiere aprobación de la lista cerrada de dependencias (apscheduler), se anota a futuro.
- Daemon systemd / servicio de Windows.
- Múltiples watches concurrentes con priorización (un lock por scope, serializados).
- Eje B (PostgreSQL + pgvector) y Eje C (auth) — tasks separadas.

---

## 4. Criterios de aceptación (DoD)

- [x] `metatracer watch --scope <id> --once` corre un scan del scope y termina limpiamente.
- [x] El delta se calcula sin LLM y sin red; las signatures repetidas no se re-notifican.
- [x] El payload de webhook gana `new_findings` (y el guard `PAYLOAD_KEYS` sigue pasando).
- [x] Lock por scope → un segundo watch falla limpio sin duplicar scans.
- [x] Cero dependencias nuevas; cero red fuera del pipeline estándar.
- [x] Suite completa verde + ruff limpio + cobertura ≥85%.