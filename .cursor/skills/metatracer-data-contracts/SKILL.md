---
name: metatracer-data-contracts
description: Contratos de datos compartidos de MetaTracer — valores de enums, ciclo de vida de severity, firma de deduplicación, convenciones SQLModel/Pydantic, idiomas por capa y ciclo de vida del dato personal. Usar al crear o modificar modelos, schemas, repositorios, exports JSON, migraciones o campos de reportes.
---

# Contratos de datos MetaTracer

Referencia completa: `.aicontext/tasks/README.md` (contratos compartidos) y `.aicontext/tasks/00-architecture-and-safety.md` (subtarea 0.2).

## Regla de oro

Enums en **minúsculas** en DB, JSON, API y Pydantic. La presentación (CLI/UI/Markdown) puede usar Title Case. Los enums son **cerrados**: no añadir valores sin actualizar `.aicontext/tasks/README.md` primero.

| Contrato | Valores |
| :--- | :--- |
| `finding_type` | `gps` \| `email` \| `internal_path` \| `software_version` \| `debug_comment` |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `confidence` | `high` \| `medium` \| `low` |
| `detector_method` | `rule` \| `heuristic` \| `agent` |
| `reasoning_depth` | `brief` \| `standard` \| `detailed` (default `standard`) |
| `run.status` | `pending` \| `running` \| `completed` \| `failed` \| `aborted` |
| `extraction_status` | `ok` \| `skipped` \| `failed` |
| `skip_reason` | `unsupported_type` \| `too_large` \| `out_of_scope` \| `duplicate_hash` \| `empty_body` |
| `namespace` | `exif` \| `xmp` \| `pdfinfo` \| `iptc` \| `http` \| `html` \| `js` |
| `feedback.vote` | `up` \| `down` (TASK-13, v2.1+) |

## Modelos (SQLModel)

- **`Run`**: `target_input` y `allowed_scope` como Text (JSON serializado); `scope_confirmed` bool default `False`; contadores `total_assets`/`total_findings`; `executive_summary` Optional Text (párrafo del nodo de summary de TASK-05; el reporte lo prefiere al texto heurístico).
- **`Asset`**: `file_hash_sha256` indexado; índice compuesto `(run_id, file_hash_sha256)`; `skip_reason` del enum de arriba.
- **`RawMetadataItem`**: `id` int autoincrement (única excepción a UUID); `namespace` ∈ `exif`/`xmp`/`pdfinfo`/`iptc`/`http`/`html`/`js`; `value` siempre texto sanitizado, **nunca bytes**; truncar >2 KB con marca `[truncated]`.
- **`Finding`**: `severity` **Optional, NULL hasta clasificar**; `severity_justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps`, `title` y `agent_model_used` todos Optional. `title` solo lo escribe una evaluación de agente real (no el fallback); el reporte cae a la plantilla por tipo si es NULL.
- **`AgentLog`**: tokens, `model_name`, `latency_ms`, `raw_response` (salida estructurada; no guardar el prompt completo si contiene secretos).
- **`FindingFeedback`** (TASK-13, v2.1+): `vote` (`up`/`down`), `severity_before`/`severity_after` (la After **distinta** y en la dirección del vote), `reason` Optional Text truncado a ~150 chars (**nunca** viaja al LLM), `created_at`. Un `finding_id` admite **un solo** feedback activo (upsert); no se exporta a reportes ni al dashboard.

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

## Idiomas por capa

- Reportes exportados (Markdown/JSON): **inglés**.
- UI/CLI: **inglés**.
- Documentación (`.aicontext/`): **español**.

## Repositorios

`RunRepository`, `AssetRepository`, `RawMetadataRepository`, `FindingRepository`, `AgentLogRepository`: CRUD mínimo + `list_by_run`. **Sin lógica de negocio** en la capa de acceso a datos.

`FeedbackRepository` (TASK-13): `create`, `get_by_finding`, `upsert_by_finding`, `list_recent`, `delete` — mismo estilo CRUD mínimo.

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
