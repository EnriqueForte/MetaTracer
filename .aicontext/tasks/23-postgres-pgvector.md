# TASK-23 — Plataforma v3.0, Eje B: PostgreSQL + pgvector

**Fuente:** [12-platform-v3.md](../features/12-platform-v3.md) (sección 3)
**Estado:** implementada 2026-09-17. Suite: 576 passed + ruff limpio + cobertura 91.57% (≥85%).
**Dependencias:** TASK-00 a TASK-22.

## Objetivo

Eliminar SQLite como limitación física de la plataforma: soporte de
PostgreSQL como motor (lecturas concurrentes), migraciones formales con
Alembic, y el índice de conocimiento (RAG) sobre **pgvector**, todo detrás de
las interfaces existentes (cero cambios en el pipeline de agentes).

## Subtareas cerradas

### 23.1 Motor (`db/engine.py`)

- `create_db_engine` valida la URL y acepta `postgresql+asyncpg`. Un
  `postgresql://` pelado (psycopg2, sync y no-lista) se rechaza con `ValueError`
  en el arranque; igual cualquier backend distinto de sqlite/postgresql.
- En Postgres **no** se instala el listener de `PRAGMA foreign_keys` (el
  servidor impone las FK); en SQLite el comportamiento legacy queda intacto.
- Trampa resuelta: `str(engine.url)` **enmascara la contraseña** (`***`) en
  SQLAlchemy 2.x; para reconstruir la URL conectable se usa
  `engine.url.render_as_string(hide_password=False)`.

### 23.2 Migraciones Alembic (`db/migrations/`)

- Sin `alembic.ini`: la config se construye programáticamente
  (`_alembic_config`); el CLI `alembic` no es el punto de entrada soportado.
- `init_db(engine)` hace dispatch por backend:
  - **Postgres**: `CREATE EXTENSION IF NOT EXISTS vector` + `command.upgrade(_cfg, "head")`
    ejecutado en `asyncio.to_thread` (el env async de Alembic gestiona su propio loop).
  - **SQLite**: bootstrap legacy (`create_all` + ALTER aditivo), sin cambios.
- `env.py` reutiliza `SQLModel.metadata` como `target_metadata`
  (los modelos son la fuente de verdad; migración inicial generada con
  `alembic revision --autogenerate` contra el Postgres real).
- Las migraciones viajan empaquetadas (`package-data` en pyproject).
- Postgres aplica las FK de verdad: los tests que siembran filas necesitan
  `flush()` entre padre e hijo (no hay `relationship()` declaradas).

### 23.3 Índice vectorial (`agents/knowledge_pg.py`)

- `PgVectorKnowledgeIndex`: misma interfaz de vida que el índice FTS5
  (`rebuild()` idempotente + `search()` con los mismos post-filtros).
- Tabla derivada **`knowledge_vectors`** (no es modelo ORM, nunca es fuente de
  verdad): se borra/recrea desde `finding`. `vector(384)` + índice HNSW
  best-effort (si la build de pgvector no lo soporta, seqscan y log).
- **Embeddings hashing-trick deterministas** (decisión de producto aprobada):
  crc32 → módulo 384 con signo alternante, tokens + trigramas, L2 normalizado.
  Estable entre procesos (a diferencia de `hash()`), sin dependencias nuevas,
  mismo espacio de features que capturaba BM25 (solapamiento léxico). El
  upgrade a embeddings semánticos (all-MiniLM-L6-v2 vía ONNX) solo exige
  sustituir `_embed` — la geometría 384 ya coincide.
- Score = `1 - cosine_distance` acotado a `[0, 1]` ("mayor es mejor", como el
  bm25 de FTS5).
- `KnowledgeRetriever` resuelve el backend perezosamente por dialecto:
  SQLite → FTS5; Postgres con pgvector → `PgVectorKnowledgeIndex`; Postgres
  **sin** pgvector → backend no-op (`[]` siempre) con warning: la fase agente
  pierde contexto histórico pero **nunca** tumba el run (regla inviolable 5).
- `RetrievedEvidence` vive ahora en `knowledge_pg` (compartida por ambos
  backends) y se re-exporta desde `agents.knowledge`: los imports existentes
  no cambian.

### 23.4 Concurrencia de runs (producto, no técnica)

- Nueva setting `METATRACER_MAX_CONCURRENT_RUNS` (default **1**).
- El `asyncio.Lock` de un solo scan pasa a `asyncio.Semaphore(N)`;
  con N=1 el comportamiento es idéntico al histórico
  (`ScanAlreadyRunningError` inmediato, sin cola, API → 409).
- `ScanAlreadyRunningError` ahora lleva `active_run_ids` (lista) y conserva
  `active_run_id` (compatibilidad). Con N>1 los slots liberados apuntan
  `active_run_id` a un run vivo, o `None` si queda vacío.
- El lock de watch por scope (TASK-22) y todo el safety no cambian.

### 23.5 Despliegue

- `docker-compose.yml`: servicio `db` (imagen `pgvector/pgvector:pg17`) bajo
  `profiles: ["postgres"]` — `docker compose --profile postgres up`. Sin
  `METATRACER_ALLOW_LOOPBACK`; la contraseña del compose es un default LOCAL
  (override con `POSTGRES_PASSWORD`).
- `.env.example` documenta la URL Postgres y `METATRACER_MAX_CONCURRENT_RUNS`.

## Contratos de datos

- **Sin cambios** en enums, severity lifecycle, `dedup_signature` ni idiomas.
- El esquema Postgres sale de los mismos modelos SQLModel (enums nativos PG,
  `TIMESTAMPTZ`, UUIDs `VARCHAR(32)`-like via `AutoString`).
- `knowledge_vectors` es una tabla derivada: nunca fuente de verdad, no es
  modelo ORM, y puede borrarse sin perder datos.

## Cadena de suministro (aprobado 2026-09-17)

| Paquete | Uso | Justificación |
| :--- | :--- | :--- |
| `asyncpg>=0.29.0` | driver async de PostgreSQL | Eje B; único driver async soportado |
| `alembic>=1.13.0` | migraciones de esquema | sustituye el ALTER aditivo en Postgres |
| `pgvector>=0.3.0` | tipos/pgvector plumbing | índice vectorial del Eje B |

La lista cerrada de TASK-00 (0.1.3) se actualizó en el mismo cambio.

## Tests

- **Unit** (siempre corren, 100% locales):
  - `tests/unit/test_engine_backends.py` — validación de URLs y dispatch.
  - `tests/unit/test_knowledge_pg.py` — embeddings (determinismo, normalización,
    similitud/desimilitud), formato vector, no-op con snippet vacío.
  - `tests/unit/test_orchestrator_concurrency.py` — semáforo: límite 1 = lock
    histórico; límite 2 permite 2 y rechaza el 3; mensaje con runs activos.
- **Integración Postgres** (skip sin servidor — `METATRACER_TEST_PG_URL`):
  `tests/integration/test_postgres_backend.py`: migraciones idempotentes,
  FKs reales, retriever e2e con score=1.0, rebuild idempotente. Cada test usa
  una BD efímera (`CREATE DATABASE` en autocommit, drop al final).

## Fuera de alcance (deliberado)

- Embeddings ONNX (`all-MiniLM-L6-v2`): la interfaz queda lista; solo falta
  sustituir `_embed` (requiere aprobar `onnxruntime` + `tokenizers`).
- `--cron` real y daemon systemd (Eje A pendiente).
- Migrar datos SQLite→Postgres (el operador usa `kb export/import` y
  `scope export/import` para lo relevante).
- Relajar el lock de watch por scope.
