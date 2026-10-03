# TASK-30: Borrado de runs y política de retención (v3.2)

**Módulo:** `db/models.py`, `db/repositories.py`, migraciones, `api/runs.py`, `cli/main.py`, Web V2 History
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P1-4
**Dependencias:** TASK-28
**Estado:** **Pendiente** (planificada 2026-10-03).

---

## 1. Objetivo técnico

Los findings contienen datos personales (emails, GPS, rutas con nombres de usuario). Hoy no hay forma de borrarlos: `RunRepository.delete` existe pero no está expuesto, y las FKs de `asset`, `finding`, `raw_metadata_item`, `agent_log`, `feedback` y `webhook_delivery` no tienen `ON DELETE CASCADE`, así que un borrado manual deja huérfanos o falla con `PRAGMA foreign_keys=ON`.

## 2. Subtareas

### 30.1 Borrado consistente

- `RunRepository.delete_cascade(run_id)` en una transacción, en orden: feedback → agent_log → findings → raw_metadata → assets → webhook_deliveries → run. Alternativa: `ON DELETE CASCADE` vía migración Alembic + bootstrap SQLite (decidir y documentar; preferir borrado explícito para no depender del backend).
- Eliminar también las entradas derivadas del índice de conocimiento (FTS5 / `knowledge_vectors`) del run.
- Borrar reportes exportados de `reports/` asociados al run (opcional, flag).
- Rechazar el borrado de un run activo (409).

### 30.2 Superficies

- API: `DELETE /api/runs/{id}` (operator + CSRF).
- CLI: `metatracer runs delete <id>` con confirmación (`-y` para no interactivo).
- Web V2: acción "Delete run" en History y en la vista del run, con diálogo de confirmación; oculta para viewers.

### 30.3 Retención automática

- `METATRACER_RETENTION_DAYS` (default vacío = sin retención). Barrido al arrancar y cada 24 h en la API; `metatracer runs prune` en la CLI.
- Los runs referenciados como baseline de `watch` siguen la misma política (documentar el efecto en los deltas).

## 3. Fuera de alcance

- Anonimización parcial (mantener estadísticas sin datos personales).
- Borrado selectivo de findings individuales.

## 4. Tests mínimos

- Borrar un run con assets, findings, feedback, logs y deliveries → cero filas huérfanas en SQLite y PostgreSQL.
- Borrar run activo → 409; viewer → 403.
- Retención: runs más antiguos que N días se borran; los recientes no.
- Índice de conocimiento sin referencias al run borrado.

## 5. Criterios de aceptación (DoD)

- [ ] Un operador puede borrar cualquier run terminal desde API, CLI y Web V2.
- [ ] Sin huérfanos tras el borrado en ambos backends.
- [ ] Retención configurable documentada en README y `.env.example`.
- [ ] Suite verde + ruff limpio + cobertura ≥85%.
