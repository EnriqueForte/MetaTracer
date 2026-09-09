# TASK-10: Gestión de scopes (v2.0)

**Módulo:** Plataforma — gestión de scopes  
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md)  
**Dependencias:** TASK-00 … TASK-09 (v1.0–v1.2 cerradas), fase v2.0  
**Estado:** Cerrada

---

## 1. Objetivo técnico

Primer slice de la fase v2.0 *Plataforma*: convertir el scope autorizado — que hoy se
teclea a mano en cada scan y vive solo en `Run.allowed_scope` — en **una entidad
persistente, reutilizable y gestionable**. Sin esto no hay "producto de gestión de
scopes" ni base para el dashboard agregado ni las notificaciones (v2.0).

Qué aporta de producto:

- El operador define una vez el conjunto de dominios autorizados de un engagement
  (con nombre y descripción) y lo reutiliza en todos sus scans.
- La Web UI lo consume al lanzar un scan (`scope_id` en vez de teclear dominios).
- El scan **congela** el scope en el `Run` como hasta ahora: editar o borrar un scope
  guardado nunca altera runs pasados ni relaja el gate de scope en curso.

Restricciones heredadas (invariantes, no tocarlas):

- El scope **nunca se infiere** de los targets. Seguirá exigiéndose `scope_confirmed=True`.
- `ScopeValidator` (con su normalización y comodines `*.`) es la fuente de verdad de
  *matching*; la entidad `Scope` solo **almacena** las entradas normalizadas.
- Se **conserva** el flujo actual por si el usuario quiere teclear dominios ad-hoc:
  `scope_domains` sigue siendo válido en `ScanRequest` y en el wizard. Precedencia:
  si viajan ambos, el servidor rechaza con 422 (ambigüedad), nunca mezcla.

---

## 2. Subtareas

### 10.1 Contratos

Nuevo modelo `Scope` (en `metatracer.db.models`), sin tocar los demás:

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `str` UUID4, PK | como las demás entidades |
| `name` | `str` | **único**, case-insensitive; `1..64` chars tras strip |
| `description` | `str \| None` | opcional |
| `domains` | `str` Text | JSON list de dominios (mirror de `Run.allowed_scope`) |
| `created_at` | `DateTime(timezone=True)` | UTC, default `_utc_now()` |

Reglas de dominio (consistentes con el resto del código):

- Cada entrada se guarda **normalizada** con `normalize_host` (minúsculas, sin
  scheme/puerto/path, comodines `*.` permitidos). Entradas vacías o que normalizan a
  `""` se descartan en el momento de persistir.
- Sin `domains` → 422 (un scope vacío no audita nada). Con `name` duplicado → 409.
- `name`, `description` y `domains` se **escaparían** en el render (Jinja autoescape);
  los valores entran siempre vía JSON API y salen por `x-text`, nunca por `x-html`.
- `null` / `""` en `name` o `domains` → 422 antes de tocar la BD.

Actualizar **antes** de persistir valores nuevos: `.aicontext/tasks/README.md`
(tabla de tasks y versión del backlog) y el [skill de contratos](../../.cursor/skills/metatracer-data-contracts/SKILL.md).

### 10.2 Modelo y repositorio

- Definir `Scope` en `metatracer/db/models.py`.
- `ScopeRepository` en `metatracer/db/repositories.py`:
  - `create(scope)`, `get(id)`, `get_by_name(name)`, `update(scope)`, `delete(id)`,
    `list_all()`.
  - `update` = merge+commit (mismo patrón que `RunRepository`).
- **Intentar añadir la tabla con el mecanismo existente** de `init_db` (`create_all` +
  `_add_missing_nullable_columns`). Una tabla nueva se crea sola; no requiere
  migración. Si aparece un caso que requiera migración real, documentarlo en un ADR
  antes de tocar nada (Alembic queda **fuera de alcance**).

### 10.3 API `SCORES_*` (TASK-10)

Convención de naming del proyecto: *endpoint de scopes = `scopes`* **siempre**
(distinto de los `score`/`scores` de la rúbrica de clasificación heurística).

Rutas en `metatracer/api/scopes.py` (prefix `/api/scopes`), todas vía los repos:

| Método | Ruta | Código | Comportamiento |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/scopes` | 201 | Crear; `409` si `name` duplicado (case-insensitive) |
| `GET` | `/api/scopes` | 200 | Listar, ordenados por `created_at.desc()` |
| `GET` | `/api/scopes/{scope_id}` | 200 / 404 | Detalle |
| `PUT` | `/api/scopes/{scope_id}` | 200 / 404 | Reemplazo completo (no PATCH) |
| `DELETE` | `/api/scopes/{scope_id}` | 204 / 404 | Borrar; los runs pasados no cambian |

Validación con Pydantic (esquemas en `metatracer/api/scopes.py` junto a las rutas,
o en `metatracer/api/schemas.py` si prefieres separarlos):

- `ScopeCreate`: `name: str` (strip, `1..64`), `description: str | None`, `domains: list[str]` non-empty tras strip.
- `ScopeUpdate`: mismos campos.
- Respuestas: `ScopeResponse` con `domains` ya normalizado (lo que quedó persistido) y `total_domains`.

Casos de error HTTP (códigos al estilo de `runs.py`):

- `404` → `detail="scope not found"` (consistente con `runs.py`).
- `409` → `detail="a scope with this name already exists"`.
- `422` → validación (Pydantic/FastAPI, igual que `runs.py`).

### 10.4 Integración con el scan (código compartido)

Mantener el **contrato de `ScanRequest` intacto** para CLI y compatibilidad: el
`scope_domains` listo sigue aceptándose.

En la capa de presentación (Web UI):

- El wizard (`index.html`) obtiene `GET /api/scopes` y muestra un `select` de scopes
  guardados **además** del campo de texto de dominios.
- Con un scope seleccionado, `POST /api/runs` envía **o** `scope_domains` (manual)
  **o** `scope_id` (nuevo, opcional) — nunca ambos; el servidor valida.
- `ScanRequest` gana un campo opcional `scope_id: str | None`. La resolución
  `scope_id → domains` vive en `services/orchestrator.py` (o en un servicio nuevo
  `services/scopes.py` si prefieres separarlo): `ScopeRepository.get` + `normalize_host`
  + validación, y **no** en la capa web.
- El `Run` se persiste exactamente igual que hoy (`allowed_scope` con los dominios
  resueltos); **no** añadimos FK `run.scope_id` en este slice.

### 10.5 Web UI

- Página `/scopes` (`metatracer/api/templates/scopes.html`) con Alpine.js:
  - Formulario de creación/edición (inline, sin PATCH).
  - Tabla de scopes (nombre, dominios, fecha, acciones editar/borrar).
  - Filtros y mensajes de error/éxito renderizados con `x-text` (nunca `x-html`).
- Nav en `base.html`: enlace `Scopes` junto a `New scan` / `History`.
- `index.html`: select de scopes guardados + manejo del caso manual (texto) / guardado.

### 10.6 Safety y persistencia

- **Cero bytes de archivos** (no aplica aquí: solo texto).
- **Cero rastro de secretos**: `name`/`description`/`domains` se sanitizan antes de
  cualquier log (reusar `sanitize_for_log` si aparecen en mensajes).
- **No relajar** el gate de scope: seguir exigiendo `scope_confirmed=True` y
  `ScopeValidator` en el runtime.
- El `Scope` borrado **no** modifica runs ya persistidos (se copia el dominio en
  `Run.allowed_scope`, no se referencian por FK).

---

## 3. Fuera de alcance

- Multi-usuario/autenticación (sigue sin auth en v2.0; proteger por bind).
- Alembic / migraciones DB, `run.scope_id` FK, soft-delete, versionado de scopes.
- PATCH en la API (solo PUT completo).
- Dashboard agregado y notificaciones de la fase v2.0 (siguientes slices).
- Import/export de scopes, wildcards `*.` en la UI, PSL.

---

## 4. Tests mínimos

- `tests/unit/test_scope_repository.py` — CRUD completo, `get_by_name` case-insensitive,
  `list_all` ordenado, `delete` devuelve `False` si no existe, invalidación ok.
- `tests/unit/test_scope_normalization.py` — persistir normaliza con `normalize_host`;
  entradas vacías se descartan; `domains=[]` → error.
- `tests/integration/test_api_scopes.py` — CRUD completo sobre ASGI: 201/200/204/404,
  `409` por nombre duplicado, `422` con `name=""` o `domains=[]`, **sin tocar**
  inventar valores de `finding_type` ni `evidence`.
- `tests/integration/test_api_scope_scan_integration.py` — POST `/api/scopes` →
  POST `/api/runs` con `scope_id` hace el scan con el `allowed_scope` resuelto;
  `run.scope` == dominios del scope; `scope_id` desconocido → 404; `scope_id` +
  `scope_domains` juntos → 422; borrar el scope tras el run **no** altera el run.
- El resto de la suite (unit + integration + agents) sigue verde con la adición.

---

## 5. Criterios de aceptación (DoD)

- [x] Crear un scope y verlo en `GET /api/scopes`; el `name` es único (case-insensitive).
- [x] Un scan lanzado con `scope_id` persiste `Run.allowed_scope` con los dominios resueltos.
- [x] Un scan ad-hoc (sin `scope_id`) sigue funcionando igual que en v1.x.
- [x] Borrar un scope no rompe ni modifica runs ya persistidos.
- [x] La Web UI permite crear, listar, editar y borrar scopes, y usarlos en el wizard.
- [x] Cero datos de bytes/secretos; cero relajación del safety gate.
- [x] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio.