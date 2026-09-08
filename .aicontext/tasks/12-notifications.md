# TASK-12: Notificaciones (v2.0)

**Módulo:** Plataforma — notificaciones
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md)
**Dependencias:** TASK-10, TASK-11 (v2.0 en curso), TASK-00 … TASK-09
**Estado:** Cerrada

---

## 1. Objetivo técnico

Último slice de **v2.0 Plataforma**. El dashboard (TASK-11) responde preguntas
*sobre el pasado*: qué se ha escaneado, con qué resultados. Las notificaciones
responden a *lo que acaba de pasar*: cuando un scan termina o falla, el operador
lo ve **sin ir a buscarlo**.

Diseño, coherente con el resto de v2.0:

- **Cero dependencias nuevas** (lista cerrada de TASK-00): cola en memoria, sin
  Redis, sin worker, sin envío por email. Al reiniciar el proceso se vacía.
- **Cero acoplamiento**: el hook vive en el orquestador (único punto de fin de
  run) pero la cola es un bus pub/sub inyectado, exactamente como
  ``on_progress`` — el pipeline no sabe que existe.
- **Sin nuevo enum**: ``kind`` reutiliza ``run.status`` (``completed``/``failed``);
  la severidad del comentario (``info``) es un enum de ``severity`` existente.
- **Solo lectura por API**: ``GET /api/notifications`` nunca escribe; el borrado
  es manual y por **índice de cola** (los eventos viven en memoria, no se
  persisten, no hay ``notification.id`` estable).

El hook no se monta en el CLI: `scan` es síncrono y terminal, la notificación se
muestra en pantalla. Solo `start_scan` (API, background) emite al bus.

---

## 2. Subtareas

### 12.1 Contratos (tipos y reglas)

Cero enums nuevos. Tipos derivados de contratos existentes:

| Campo | Tipo | Regla |
| :--- | :--- | :--- |
| `id` | `int` | índice de **listado** corriente (0-based, newest-first); **renumera tras cada borrado** |
| `kind` | `run.status` | `completed` \| `failed` |
| `run_id` | `str` | UUID4 del run |
| `target` | `str` | primer target del run (igual que el historial) |
| `total_assets` | `int` | contador del run |
| `total_findings` | `int` | contador del run |
| `error_message` | `str \| None` | solo en `failed`; ya saneado por el orquestador |
| `created_at` | `datetime` | timezone-aware UTC, igual que el resto del stack |

Reglas de productos:

- `kind` = `completed` → `error_message` siempre `null`; `kind` = `failed` →
  `error_message` presente (el orquestador garantiza mensaje saneado).
- El orden de listado es **newest first**, igual que el historial de runs.
- Tope de cola: **100** eventos; el más antiguo se descarta (memoria acotada,
  mismo espíritu que `ProgressBus`).
- El borrado es por **índice de cola** en el orden de listado. Un índice inválido
  (fuera de rango, o ya borrado) → **404** (no hay id persistente que validar).
- No persiste nada: al reiniciar la app, la campana arranca vacía.

### 12.2 Bus en memoria

Nuevo `metatracer/services/notifications.py` (sin dependencias fuera del stdlib):

```
NotificationKind = run.status  # completed | failed
class NotificationEvent(BaseModel):
    id, kind, run_id, target, total_assets, total_findings, error_message, created_at

class NotificationBus:
    def __init__(self, max_events: int = 100) -> None
    def publish(self, event: NotificationEvent) -> None   # append + descarte del más viejo
    def list(self) -> list[NotificationEvent]             # newest first, copia
    def delete(self, list_index: int) -> bool             # borra por índice de listado
```

- `publish` es síncrono (mismo hilo del event-loop) y **nunca lanza**: si el
  ``created_at`` viniera sin tz (nunca en el código real), se asume UTC.
- `delete` devuelve `False` para un índice inválido — el router traduce a 404.
- Solo texto estructurado y contadores: **nunca** snippets/bytes/secretos.

### 12.3 Hook en el orquestador

- `ScanOrchestratorService` gana un parámetro opcional `notifications:
  NotificationBus | None = None` (convención de inyección del proyecto; los
  tests lo inyectan, la app lo teje en el lifespan).
- Al finalizar el run en `_finalize_run` — que es **exactamente un punto de
  salida** para `completed` y `failed` — se emite un evento al bus **dentro del
  mismo `async with session`** (así los contadores ya son los finales).
- La emisión se envuelve en `try/except`: un bus que falle **nunca tumba el
  run** (regla inviolable 5, mismo espíritu que `_emit` para progress).
- `_create_run` no emite nada (`pending`/`running` no notifican).
- El CLI no engancha bus: notifica por pantalla, no por campana.

### 12.4 API

Nuevo router `metatracer/api/notifications.py` (prefix `/api/notifications`, tag
`notifications`):

```
GET    /api/notifications          -> 200 {total, notifications: [...]}   # newest first
DELETE /api/notifications/{index}  -> 204 | 404
```

- `NotificationResponse` en `api/schemas.py`; `kind` viaja en minúsculas
  (contrato), `error_message` solo en `failed`.
- Mapeo de Pydantic: el bus expone `NotificationEvent`, el router mapea a
  `NotificationResponse` (misma separación servicio/vista que el dashboard).
- El 404 lleva detalle claro ("notification index out of range").
- Registro en `api/app.py`.

### 12.5 Web UI

- `base.html`: campana en la nav con `Alpine.data("notifications_bell")`,
  cargando `GET /api/notifications` al inicio. Badge = nº de eventos.
- Panel desplegable: fila por evento con `x-text` (nunca `x-html`), tipo
  (`completed`/`failed`), target, contadores y, en fallos, `error_message`
  recortado.
- Fallo digno si la API no responde (la campana no rompe la página: badge oculto
  silenciosamente), y recarga manual.
- `x-cloak` ya está en el CSS; **cero `innerHTML`/`x-html`**, todos los datos
  salen por `x-text`/`textContent` (tipo, target, contadores, `error_message`).
- Sin dependencias nuevas (Alpine ya está).

---

## 3. Fuera de alcance

- Persistencia de notificaciones (sin tabla, sin migración), multiusuario,
  email/webhook/push, sonidos.
- Borrado en bloque ("clear all"), marcar leído, paginación.
- Notificaciones para `pending`/`running`/`aborted`.
- Bell/panel fuera de la Web UI (el CLI notifica por pantalla).

---

## 4. Cobertura de safety

- `GET` **solo lee**: no hay commit ni escritura — los tests lo comprueban.
- `DELETE` solo toca la cola en memoria; no hay assert ni comprobación de scope.
- Cero red nueva: ningún socket en notificaciones.
- `error_message` ya viene saneado del orquestador (`sanitize_for_log` upstream);
  el panel lo trunca a ~150 chars para render (defensa de profundidad).

---

## 5. Tests mínimos

- `tests/unit/test_notification_bus.py` — publish/list/delete: orden newest-first,
  tope de 100 descarta el más viejo, borrado por índice con 404-equivalente
  (`False`), `error_message=None` en `completed`, tz UTC en `created_at`.
- `tests/unit/test_orchestrator_notifications.py` — inyectando el bus real:
  scan feliz notifica exactamente **una** `completed` con contadores finales;
  run que falla notifica **una** `failed` con `error_message`; el bus nunca
  recibe eventos de `pending`/`running`.
- `tests/integration/test_api_notifications.py` — con el fixture ASGI de
  siempre: GET 200 con 0 notificaciones; tras una notificación sembrada (vía
  `bus.publish` sobre `app.state`): 200 con contrato (keys, `kind` en minúsculas,
  `error_message` solo en `failed`), DELETE 204 y desaparece, DELETE repetido →
  404, índice fuera de rango → 404; GET es read-only (contar antes/después).
- `tests/integration/test_notifications_page.py` — `/` 200 y el HTML contiene
  la campana (`notifications_bell`), sin requerir datos.
- Suite completa en verde: `pytest -m "not e2e"` y `ruff check src tests`.

---

## 6. Criterios de aceptación (DoD)

- [x] Un run completado/fallido vía `start_scan` (o `scan` con bus inyectado)
      produce exactamente **una** notificación con los contadores finales.
- [x] `GET /api/notifications` devuelve la cola newest-first, solo lectura.
- [x] El borrado manual por índice funciona (204) y los índices inválidos dan 404.
- [x] La campana en la nav muestra el badge y el panel; cero `x-html`/`innerHTML`.
- [x] Sin dependencias nuevas ni tabla nueva; el pipeline no conoce el bus.
- [x] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio.