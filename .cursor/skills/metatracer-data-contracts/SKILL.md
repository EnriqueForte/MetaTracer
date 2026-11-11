---
name: metatracer-data-contracts
description: Contratos de datos compartidos de MetaTracer — valores de enums, ciclo de vida de severity, firma de deduplicación, convenciones SQLModel/Pydantic, idiomas por capa y ciclo de vida del dato personal. Usar al crear o modificar modelos, schemas, repositorios, exports JSON, migraciones o campos de reportes.
---

# Contratos de datos MetaTracer

Referencia completa: `.aicontext/tasks/README.md` (contratos compartidos) y `.aicontext/tasks/00-architecture-and-safety.md` (subtarea 0.2).

## Regla de oro

Enums en **minúsculas** en DB, JSON, API y Pydantic. La presentación (CLI/UI/Markdown) puede usar Title Case. Los enums son **cerrados**: no añadir valores sin actualizar `.aicontext/tasks/README.md` primero. No quedan enums reserved. Investigations: TASK-36. Detectores de red y OOXML/ODF: TASK-37. Conectores: TASK-38. Redacción de export: TASK-39. Specs 40–42 siguen reserved — ver `MEMORY.md`.

| Contrato | Valores |
| :--- | :--- |
| `finding_type` | `gps` \| `email` \| `internal_path` \| `software_version` \| `debug_comment` \| `internal_endpoint` \| `cloud_storage` |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `confidence` | `high` \| `medium` \| `low` |
| `detector_method` | `rule` \| `heuristic` \| `agent` |
| `reasoning_depth` | `brief` \| `standard` \| `detailed` (default `standard`) |
| `run.status` | `pending` \| `running` \| `completed` \| `failed` \| `aborted` |
| `extraction_status` | `ok` \| `skipped` \| `failed` |
| `skip_reason` | `unsupported_type` \| `too_large` \| `out_of_scope` \| `duplicate_hash` \| `empty_body` \| `robots_disallow` |
| `namespace` | `exif` \| `xmp` \| `pdfinfo` \| `iptc` \| `http` \| `html` \| `js` \| `ooxml` \| `odf` |
| `feedback.vote` | `up` \| `down` (TASK-13, v2.1+) |
| `user.role` | `operator` \| `viewer` (TASK-24, v3.0 Eje C) |
| `triage_status` | `open` \| `confirmed` \| `false_positive` \| `fixed` (TASK-35; default `open`; solo operador) |
| `investigation.status` | `open` \| `closed` (Fase 3; agrupa runs, no aísla) |
| `correlation.kind` | `email` \| `gps_point` \| `internal_endpoint` \| `software_version` \| `document_id` \| `device_serial` \| `author_string` |

## Modelos (SQLModel)

- **`Run`**: `target_input` y `allowed_scope` como Text (JSON serializado); `scope_confirmed` bool default `False`; contadores `total_assets`/`total_findings`; `executive_summary` Optional Text (párrafo del nodo de summary de TASK-05; el reporte lo prefiere al texto heurístico).
- **`Asset`**: `file_hash_sha256` indexado; índice compuesto `(run_id, file_hash_sha256)`; `skip_reason` del enum de arriba.
- **`RawMetadataItem`**: `id` int autoincrement (única excepción a UUID); `namespace` ∈ `exif`/`xmp`/`pdfinfo`/`iptc`/`http`/`html`/`js`/`ooxml`/`odf`; `value` siempre texto sanitizado, **nunca bytes**; truncar >2 KB con marca `[truncated]`.
- **`Finding`**: `severity` **Optional, NULL hasta clasificar**; `severity_justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps`, `title` y `agent_model_used` todos Optional. `title` solo lo escribe una evaluación de agente real (no el fallback); el reporte cae a la plantilla por tipo si es NULL.
- **`AgentLog`**: tokens, `model_name`, `latency_ms`, `raw_response` (salida estructurada; no guardar el prompt completo si contiene secretos).
- **`FindingFeedback`** (TASK-13, v2.1+): `vote` (`up`/`down`), `severity_before`/`severity_after` (la After **distinta** y en la dirección del vote), `reason` Optional Text truncado a ~150 chars (**nunca** viaja al LLM), `created_at`. Un `finding_id` admite **un solo** feedback activo (upsert); no se exporta a reportes ni al dashboard.
- **`User` / `UserSession`** (TASK-24, v3.0 Eje C): una fila `user` por instalación (multi-tenant deferido a v3.1); `password_hash` es el formato versionado `pbkdf2_sha256$<iteraciones>$<salt_b64>$<hash_b64>` (stdlib, cero dependencias). `user_session.token_hash` guarda el **SHA-256 hex** del token — nunca el token; `expires_at` aware UTC se valida en el servidor. `password_hash` y `token_hash` no salen nunca en respuestas API.

Convenciones: UUIDs como `str` (UUID4); timestamps timezone-aware UTC; `PRAGMA foreign_keys=ON`; sin tipos exclusivos de SQLite (migración a PostgreSQL en el horizonte).

## Ciclo de vida de un finding

1. **Detectores** (TASK-02) emiten drafts: `severity=NULL`, `detector_method="rule"`. Nunca asignan severity.
2. **Heurístico** (TASK-03) rellena `severity` + plantillas en inglés; `agent_model_used` queda vacío.
3. **Agente** (TASK-05) puede ajustar severity dentro de la rúbrica y reescribir prosa; rellena `agent_model_used` (o `"heuristic-fallback"` si el LLM falla). No puede tocar `finding_type` ni `evidence_snippet`.
4. **Reportes** (TASK-04) funcionan con cualquiera de los dos estados; campos de prosa vacíos → `Not generated (heuristic baseline)`, nunca crash. Si existen `Run.executive_summary` / `Finding.title`, el reporte los usa en lugar de la prosa heurística/plantilla.

## Dedup

```python
dedup_signature = sha256(f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}")
```

Unique constraint `(asset_id, dedup_signature)`. Insertar ignorando conflictos; al consolidar, `field_source` se concatena con `" | "` (ordenado, sin duplicados).

`dedup_signature` incluye el `asset_id`, que es nuevo en cada run. Para comparar entre runs (watch, `/api/compare`) se usa `finding_identity = sha256(f"{asset.final_url}:{finding_type}:{evidence_snippet.strip().lower()}")` (TASK-35).

## Triage (TASK-35)

`Finding.triage_status` (no nulo, default `open`, indexado), `triage_note` (≤500), `triaged_by` (user id, `local` con auth off, `cli`), `triaged_at` UTC. Lo cambia solo un operador por `PUT /api/runs/{run_id}/findings/{finding_id}/triage` o `metatracer findings triage`. No toca `severity` ni `evidence_snippet`. `false_positive` queda fuera de los exports (salvo `include_false_positives`) y de los conteos del dashboard (contador `dismissed` aparte). No genera feedback para el clasificador: son decisiones distintas.

## Idiomas por capa

- Reportes exportados (Markdown/JSON): **inglés**.
- Web UI: **español**. CLI: **inglés**.
- Documentación (`.aicontext/`): **español**.

## Repositorios

`RunRepository`, `AssetRepository`, `RawMetadataRepository`, `FindingRepository`, `AgentLogRepository`: CRUD mínimo + `list_by_run`. **Sin lógica de negocio** en la capa de acceso a datos.

`FeedbackRepository` (TASK-13): `create`, `get_by_finding`, `upsert_by_finding`, `list_recent`, `delete` — mismo estilo CRUD mínimo.

## Scopes portables (TASK-19, v2.2)

`metatracer/scopes/portable.py` — import de scopes desde archivo JSON, espejo de `knowledge/portable.py`:

- **Formato del archivo**: `{"format_version": 1, "scopes": [{"name", "description", "domains"}]}`. Solo `format_version` 1; campos extra fuera del contrato → rechazo con error.
- **Normalización**: cada dominio con `normalize_host` (minúsculas, sin scheme/puerto/path, comodines `*.`); entradas vacías se descartan; entrada sin dominios válidos → `ValueError` (nunca reasignar).
- **Semántica**: idempotente por `name` case-insensitive — si el scope ya existe **se omite** (no se pisa, no se actualiza). No borra nada, no hay red, no hay bytes (solo `name`/`description`/`domains`).
- **Superficies**: CLI `scope import --file` + API `POST /api/scopes/import` (UploadFile → temp → import) con respuesta `{"imported": n, "skipped": m}`. `ValueError` del parser → exit 1 / 422, nunca un insert a medias.

## RAG ligero (TASK-14, v2.1+; dispatch por backend desde TASK-23)

`metatracer/agents/knowledge.py` + `metatracer/agents/knowledge_pg.py`:

- **`KnowledgeIndex`** (SQLite) — índice FTS5 (virtual table `knowledge_fts`) sobre findings históricos. `rebuild()` lo reconstruye (idempotente), `search(query, finding_type=None, exclude_finding_id=None, limit=5)` devuelve `RetrievedEvidence` rankeados. La tabla derivada **nunca es fuente de verdad**; se borra/recrea.
- **`PgVectorKnowledgeIndex`** (PostgreSQL, TASK-23) — índice vectorial pgvector (tabla derivada `knowledge_vectors`, `embedding vector(384)`, HNSW best-effort, distancia coseno). Mismos `rebuild()`/`search()` y post-filtros que el FTS5; `score = 1 - cosine_distance` acotado a `[0, 1]`. Embeddings 384-d: MiniLM ONNX local (TASK-40, extra `[onnx]`) o hashing-trick (crc32 módulo 384, tokens + trigramas, L2) si ONNX no carga.
- **`KnowledgeRetriever`** — construye la query desde los campos cerrados del payload (`evidence_snippet` + `field_source` + `finding_type`), sin red y sin texto libre del operador. Índice vacío → no-op (`[]`). Resuelve el backend perezosamente por dialecto: SQLite → FTS5; Postgres con pgvector → `PgVectorKnowledgeIndex`; Postgres **sin** pgvector → backend no-op con warning (la fase agente pierde contexto histórico pero nunca tumba el run, regla inviolable 5).
- **`RetrievedEvidence`** (dataclass read-only, vive en `knowledge_pg` y se re-exporta desde `agents.knowledge`): `finding_id`, `run_id`, `finding_type`, `evidence_snippet`, `severity | None`, `title | None`, `created_at | None`, `score`.
- Inyección: `AgentPipeline(..., knowledge=KnowledgeRetriever)` adjunta `entry["retrieved_evidence"]` **fuera** del payload cerrado; `AnalyzeContextNode` lo fusiona al prompt como guía **no autoritativa** (nunca como evidencia del finding actual). Trazabilidad: nota `retrieved_evidence_used=<n>` en `guard_notes` (AgentLog), nunca los snippets.
- FTS5 sanitiza la query (tokens alfanuméricos AND-phrases) porque los snippets llevan `.` `/` `@` que romperían la sintaxis.
- Endpoint read-only `GET /api/knowledge/search?q=...&finding_type=...&limit=...`.

## Ciclo de vida del dato personal (amenaza 14)

MetaTracer **es** una herramienta que encuentra datos personales: GPS, emails, nombres en paths.
Eso no la exime de tratarlos con cuidado; los hace más sensibles, no menos. Esto fija el ciclo
de vida del dato personal dentro del producto. No es una política de privacidad (eso es decisión
de producto y legal, fuera del código); es lo que el código hace con el dato una vez extraído.

- **Minimización en origen:** el extractor ya trunca a ~2 KB y descarta blobs. No se persiste
  nada que no sea necesario para el finding. Un campo de metadata que no aporta evidencia no se
  guarda "por si acaso".
- **Persistencia:** `RawMetadataItem.value` es siempre texto sanitizado, nunca bytes. La base de
  datos (`data/*.db`) está en `.gitignore` y nunca entra en la imagen Docker ni en un commit.
- **Exposición:** el dato personal aparece en el reporte porque es la evidencia del hallazgo,
  pero el reporte es un artefacto que el hunter genera y controla. No se envía a terceros, no se
  sube a ningún servicio, y el `compliance_notice` recuerda que el objetivo es que el programa
  lo elimine, no explotarlo.
- **Logs:** un valor con datos personales no se interpola crudo en un mensaje de log (ver
  `metatracer-safety-rules`, sección "Logging seguro").
- **LLM:** el payload al modelo contiene el snippet de evidencia, no el campo completo ni el
  archivo. El `ContextOptimizer` recorta a los campos del contrato.
- **Borrado:** no hay retención automática ni envío externo. El dato vive en la SQLite local del
  hunter y en los reportes que él genera; eliminarlos es eliminar el dato.
