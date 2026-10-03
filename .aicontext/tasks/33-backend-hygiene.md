# TASK-33: Higiene del backend (SSE, webhooks, BD, auth) (v3.2)

**Módulo:** `services/progress.py`, `api/runs.py`, `api/webhooks.py`, `db/`, `services/watch.py`, `api/auth.py`, `agents/`, `classification/`, `api/knowledge.py`
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P2 (backend)
**Dependencias:** TASK-28, TASK-31
**Estado:** **Pendiente** (planificada 2026-10-03).

---

## 1. Objetivo técnico

Cerrar los defectos P2 de operación y rendimiento del backend.

## 2. Subtareas

### 33.1 SSE tras evicción del historial

- `api/runs.py` stream: si el run es terminal en BD y el `ProgressBus` no tiene historial, emitir un evento terminal sintético con el estado persistido y cerrar. No suscribirse a una cola que nunca recibirá eventos.

### 33.2 Reintentos de webhook autónomos

- Worker en el lifespan que cada N segundos barre `list_pending` y reintenta las entregas con `next_retry_at` vencido (en vez de depender del siguiente evento terminal).
- Redactar `config.headers` en cualquier log de httpx del cliente de webhooks (R4 de la revisión 2026-09-16).

### 33.3 Base de datos

- Índice compuesto `(started_at DESC, id)` en `run` (migración + bootstrap SQLite), alineado con la paginación keyset; corregir el comentario de `repositories.py`.
- Unificar `webhook_config.name` (modelo `default=None` vs migración `nullable=False`).
- Dashboard: agregaciones con `GROUP BY` en SQL en vez de cargar todos los `Finding` (`repositories.py` ~L382–427).
- `DeltaReporter`: filtrar por `allowed_scope` en SQL y obtener las firmas del baseline en una sola consulta `WHERE run_id IN (...)`.
- Shutdown ordenado: `engine.dispose()` (R7).

### 33.4 Auth

- Lockout/backoff progresivo por `username + IP` en `/api/auth/login`, con límite propio más bajo que el global.
- Invitaciones usadas/expiradas: ejecutar siempre el PBKDF2 dummy para igualar tiempos.
- First-run setup: claim atómico (lock de proceso + comprobación en BD de "ya existe un operator") para impedir dos operators concurrentes.

### 33.5 Calidad de código

- Romper el import circular `classification` ↔ `agents`: mover `FeedbackExample` a un módulo hoja (`classification/feedback.py`); `agents/__init__.py` sin imports pesados.
- Eliminar `GraphNodes` (`agents/graph.py`), sin uso.
- Compartir las regex de `detectors/debug.py` y `classification/classifier.py` en un módulo `patterns.py`.
- Corregir el comentario "one subscriber" de `ProgressBus` en `api/app.py`.

### 33.6 Operación

- `GET /api/ready`: ping a la BD (503 si falla); `/api/health` sigue siendo liveness sin estado.
- Export KB: borrar el temporal con una `BackgroundTask` al terminar la respuesta, no con un temporizador de 2 s.

## 3. Fuera de alcance

- Métricas Prometheus / OpenTelemetry.
- Versionado `/api/v1`.

## 4. Tests mínimos

- SSE de un run terminal sin historial → evento terminal y cierre.
- Entrega de webhook fallida se reintenta sin nuevos scans.
- Dashboard con 5 000 findings: número de consultas constante.
- 10 logins fallidos del mismo usuario → backoff; login correcto posterior respeta el bloqueo.
- Dos `POST /api/auth/setup` concurrentes → un solo operator.
- `python -c "import metatracer.classification.anchor"` sin error de import circular.
- `/api/ready` → 503 con la BD caída.

## 5. Criterios de aceptación (DoD)

- [ ] Ningún stream SSE queda colgado para runs terminales.
- [ ] Reintentos de webhook independientes del tráfico de scans.
- [ ] Consultas de dashboard y deltas sin N+1.
- [ ] Suite verde + ruff limpio + cobertura ≥85%.
