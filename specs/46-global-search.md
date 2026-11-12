# Spec 46 — Búsqueda global de hallazgos y metadata

**Estado:** closed (2026-11-12)  
**Agente previsto:** `ui-engineer` (API) · `v2-ui-engineer` (Web UI)  
**Skill al abrir:** `metatracer-ui` · `metatracer-platform` (paginación keyset)  
**Task:** [TASK-46](../.aicontext/tasks/46-global-search.md)

## Intención

Un operador con muchos runs no puede localizar un email, un GPS o un campo crudo sin abrir
ficha por ficha. Hoy la búsqueda es substring **dentro de un run**
(`GET /api/runs/{id}/findings?q=`, explorador de metadata por run) y FTS/pgvector cubre
solo el RAG de precedentes (`GET /api/knowledge/search`).

Esta slice añade una búsqueda **sobre datos ya persistidos** (findings y `RawMetadataItem`),
sin crawlear, sin geocoding y sin indexar cuerpos (no se almacenan).

## Alcance

- API paginada keyset (mismo estilo que el historial de runs): query sobre findings
  (`title`, `evidence_snippet`, `field_source`, URLs de asset) y raw metadata (`key`, `value`).
  Filtros: scope, run, `finding_type`, `namespace`, `severity`, `triage_status`.
- SQLite: `ILIKE` + índices. Postgres: ranking léxico; `?mode=lexical|similar` opcional
  reutilizando MiniLM/hashing-trick **ya existentes** (spec 40). No nuevo embedding API.
- UI: workspace `/search` (español). Paleta Ctrl+K: además de saltar a runs, hasta ~8 hits
  de evidencia.
- Authz: viewer lectura; operator igual. CSRF irrelevante (GET). Un solo origen.
- CLI `metatracer search` (inglés), misma consulta.

## Fuera de alcance

Crawlear URLs desde la búsqueda. Geocoding. Grafo OSINT / identidad. Indexar bodies.
Sustituir `GET /api/knowledge/search` (precedentes del agente). Segunda host / CORS.
Nuevos `finding_type`.

## Dependencias

v3.2 + specs 36–45 closed. Contrato visual: `.aicontext/ui/design-system-v2.md`.
Enums: `.aicontext/tasks/README.md` (sin valores nuevos).
