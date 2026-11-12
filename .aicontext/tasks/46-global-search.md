# TASK-46: Búsqueda global de hallazgos y metadata

**Módulo:** `api/search.py`, `services/search.py`, `db/repositories.py`, CLI `search`, `web/` `/search`  
**Spec:** [specs/46-global-search.md](../../specs/46-global-search.md)  
**Dependencias:** TASK-21 (keyset), TASK-14/40 (índice de conocimiento para `mode=similar`)  
**Agentes:** `ui-engineer`, `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-12.**

## 1. Objetivo técnico

Permitir localizar evidencia y campos crudos **entre runs** sin crawlear ni indexar cuerpos.

## 2. Subtareas

- `GET /api/search` (sesión, GET, viewer OK). Query `q` (1–200), `kind=findings|metadata|all`, `mode=lexical|similar`, filtros `run_id`, `scope_id`, `finding_type`, `namespace`, `severity`, `triage_status`, `limit`, `findings_cursor`, `metadata_cursor`.
- Repositorios: `ILIKE` con escape de `%`/`_`; keyset `created_at,id` (findings) e `id` (metadata). Índices de filtro en SQLite `init_db` y Alembic Postgres.
- `mode=similar`: reutilizar `KnowledgeRetriever` (FTS5 / pgvector). Si el índice está vacío o no hay retriever, caer a léxico. No sustituye `/api/knowledge/search`.
- CLI `metatracer search` (inglés).
- UI `/search` en español; nav Research; paleta: comando Buscar + hasta 8 hits de hallazgos.
- Regenerar OpenAPI / `schema.d.ts`.

## 3. Fuera de alcance

Crawlear. Geocoding. Grafos. Bodies. Nuevo `finding_type`. CORS.

## 4. DoD

- [x] Viewer GET 200; no hay mutación
- [x] Query no dispara red ni lee bytes de archivo
- [x] Keyset estable; cursor malformado → 422
- [x] Vitest de paleta/página; tests API de ILIKE, filtros, similar fallback
- [x] Spec 46 closed al terminar; MEMORY y backlog actualizados
