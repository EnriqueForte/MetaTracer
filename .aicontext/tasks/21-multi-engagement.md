# TASK-21: Multi-engagement y paginación del historial (v2.4)

**Módulo:** Plataforma+ — operación a escala (backlog de auditoría 2026-09-16)
**Referencia PRD:** [Interfaces](../features/06-interfaces.md), [Gestión de scopes](10-scope-management.md), [Historial](08-usability.md)
**Dependencias:** TASK-00 … TASK-20
**Estado:** **Cerrada 2026-09-16.** Implementada, testeada (528 passed, ruff limpio) y cerrada en el mismo día en que se formalizó.

---

## 1. Objetivo técnico

Hoy `ScanRequest` exige **exactamente una** fuente de scope (`scope_domains` XOR `scope_id`, validado en `ScanRequest._exactly_one_scope_source`). Un operador que ya gestiona N scopes guardados (TASK-10/19) tiene que lanzar **un run por engagement** aunque el trabajo sea el mismo tipo de auditoría sobre varios scopes. Y `GET /api/runs` tiene `_MAX_HISTORY = 200` con `limit` pero **sin paginación exponible**: la UI de `/runs` carga todo de golpe.

Esta task añade dos capacidades independientes:

1. **Multi-scope por run**: un run puede lanzarse contra la **unión de varios scopes guardados** (`scope_ids: list[str]`), con la misma garantía de scope (todo pasa por `ScopeValidator`), cero red extra y cero cambio en el pipeline (el orquestador solo resuelve la unión antes de crear el Run).
2. **Paginación del historial**: `GET /api/runs` con cursor estable y UI de History con prev/next, eliminando el tope silencioso de 200.

Invariantes que se preservan:

- **El scope no se infiere** (regla 1): la unión se construye solo de scopes guardados confirmados por el operador, nunca de los targets.
- **Cero red / cero bytes**: listar/resolver scopes es local, como TASK-19.
- **El Run sigue dueño de su snapshot** (TASK-10): se copia la unión a `Run.allowed_scope`, de modo que editar/borrar un Scope después no altera runs pasados.
- **Compatibilidad**: `scope_id` (singular) se mantiene como alias de `scope_ids=[scope_id]`; ningún cliente v2.0–v2.3 se rompe.

---

## 2. Subtareas

### 21.1 Contrato y resolución multi-scope ✅

- `ScanRequest`: añadido `scope_ids: list[str] | None`. Reglas del validador:
  - Exactamente una de `{scope_domains, scope_id, scope_ids}` (nunca mezclas) — validado por `_exactly_one_scope_source`.
  - `scope_ids` debe tener ≥1 elemento; cada elemento válido (UUID4 no vacío) — `_valid_scope_ids`.
  - `scope_id` singular se conserva y se normaliza a `scope_ids` de 1 elemento en el borde (sin cambiar el wire contract aceptado hoy).
- Orquestador: nuevo `_resolve_scope_domains_many(scope_ids)` que:
  - Carga cada scope con `ScopeRepository.get`; un id inexistente → `ScopeNotFoundError` (el API lo mapea a 404).
  - Hace la **unión con orden estable y sin duplicados** (`dict.fromkeys`), cada dominio ya normalizado (vienen normalizados de la BD).
  - Si la unión resultase vacía → `MetaTracerError` (mismo posture que hoy).
  - `ScopeValidator` se construye con la unión: **el matching no cambia**.
- Documentados en `tasks/README.md` (contratos) y en el docstring del orquestador.

### 21.2 API paginada del historial ✅

- `GET /api/runs`: paginación por **cursor** (estable bajo inserciones nuevas): `?cursor=<started_at>_<run_id>&limit=N`.
  - Respuesta: `next_cursor: str | None`, `has_more: bool` y `total` global (sin truncar) en `RunListResponse`.
  - `RunRepository.list_recent` gana un predicado de cursor (keyset sobre `(started_at, id)`, con tie-break `id desc`; `started_at` ya indexado) y fetch `limit + 1` para `has_more` sin count extra; `RunRepository.count` añadido.
  - Se mantiene `status` y `limit` (acotado a `_MAX_HISTORY` como techo del cursor).
  - El cursor viaja como `<…>Z_<run_id>` (sin `+` en la query string) y se parsea con tolerancia a `Z`/`+00:00`; malformado → 422.
- CLI `list-runs`: `--cursor`/`--limit` opcionales (paridad CLI/API).

### 21.3 Web UI ✅

- Wizard (`index.html`): selector multi-scope con checkboxes sobre `/api/scopes` que envía `scope_ids` (el servidor resuelve la unión); el campo manual `scope_domains` queda como fallback v1.x.
- History (`history.html`): Older/Newer con `next_cursor`, estado "Loading more…", contador "N runs" desde el `total` global (sin truncar) y stack de cursores para navegar hacia atrás sin refetch.

### 21.4 Tests mínimos ✅

- Orquestador (`tests/unit/test_orchestrator_multi_scope.py`): unión deduplicada de 2+ scopes; id inexistente → error antes de crear run; `Run.allowed_scope` snapshot sobrevive al borrado; normalización `scope_id`→`scope_ids`.
- Validación: mezclas inválidas (`scope_domains` + `scope_ids`, `scope_ids` vacíos) → 422; `scope_id` singular sigue funcionando (regresión, en `test_api_scope_scan_integration.py`).
- API (`tests/integration/test_api_runs_pagination.py`): paginación estable bajo inserción entre páginas (sin duplicar/derrumbes), `has_more` correcto, `next_cursor` nulo en la última página, filtro por status compuesto y cursor malformado → 422.
- UI smoke: history con paginación (`test_history_page.py`) y wizard multi-scope (`test_api_scope_scan_integration.py`).
- Guardrail: `pytest -m "not e2e"` → **528 passed**, `ruff check src tests` limpio (cobertura verificada por `ci-check.ps1`).

---

## 3. Fuera de alcance

- Intersecciones, negaciones o exclusiones de scope (`scope_a - scope_b`).
- Autenticación / multi-tenant (sigue sin auth; bind localhost o red confiable).
- Migración de datos o backfill de runs existentes.
- Paginación de findings por API (la tabla de findings ya es client-side).

---

## 4. Criterios de aceptación (DoD)

- [x] `POST /api/runs` acepta `scope_ids` (y `scope_id` singular sigue intacto); un scope inexistente → 404 con nombre.
- [x] El run persiste en `allowed_scope` la **unión** normalizada y sin duplicados; un scan multi-scope respeta el scope en cada request (sin regresión en el e2e).
- [x] `GET /api/runs` pagina con cursor estable y `has_more`/`next_cursor`; la UI de History la usa.
- [x] Wizard multi-scope funciona sin romper el flujo manual (línea de targets + confirmación visual del modal).
- [x] Cero dependencias nuevas; cero red; cero bytes persistidos extra.
- [x] Suite completa verde (528 passed) + ruff limpio + cobertura ≥85%.