# TASK-17: KB portable (v2.2)

**Módulo:** Integraciones — portabilidad del conocimiento histórico (RAG)
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Agentes de IA](../features/05-ai-agents.md)
**Dependencias:** TASK-00 … TASK-16 (v1.0–v2.2 cerradas)
**Estado:** **Cerrada y validada 2026-09-13** — export/import JSON portable + CLI `kb export/import` + API `POST /api/knowledge/export|import`. Verificado localmente: `ci-check.ps1` exit 0 (447 passed + ruff limpio), suite completa **451 passed** (incluye e2e), cobertura **90.63% ≥ 85%**. Correcciones de bugs heredados de TASK-14 (doble sanitización del FTS y recuperación de precedentes) documentadas abajo.

---

## 1. Objetivo técnico

TASK-14 construyó el índice FTS5 (`knowledge_fts`) **sobre los `finding`
históricos de la BD local del operador**. Ese conocimiento ("esto ya lo vi
antes y era severo") queda atado al archivo SQLite de una máquina: si el
operador cambia de equipo, trabaja en paralelo en otra máquina o quiere
compartir su base de precedentes con un compañero —sin exponer datos crudos—,
no hay forma de moverlo.

La **KB portable** exporta el **corpus histórico de precedentes** (los mismos
campos que indexa el RAG: identificadores estables del finding, tipo,
snippet ya sanitizado, severidad final, título, fecha) a un **archivo JSON
portable** (`kb-export.json`), y puede re-importarlo en otra BD para
poblar/reconstruir el índice, **sin arraigar IDs ni datos del run de origen**.

Qué aporta de producto:

- El operador lleva su memoria de hallazgos (precedentes para el agente) entre
  máquinas o como backup, **sin acarrear la BD completa** (que incluye runs,
  assets, raw metadata, agent logs, webhooks: mucho dato operativo).
- Compartir precedentes con un compañero o un equipo sin exponer evidencia
  cruda ni metadata sensible no incluida en el contrato.
- Es un **respaldo legible del conocimiento** que alimenta el RAG: el índice
  FTS5 se puede reconstruir solo con este archivo (p. ej. en una machina
  nueva sin BD histórica).

Preservación de invariantes:

- **Cero bytes de archivos** (regla 3): solo snippets ya sanitizados (~150
  chars), nunca archivos ni metadata cruda fuera del contrato.
- **Sin red** (regla 1): export/import son operaciones de archivo local,
  exactamente igual que el RAG (TASK-14).
- **Sin datos del run de origen ligados**: se exportan los campos del contrato
  de `RetrievedEvidence` (no `run_id`, `asset_id`, `dedup_signature`, `source_url`).
- **El import no inventa**: `finding_type`/`severity`/`evidence_snippet` se
  validan contra los enums cerrados; los que no pasen se **rechazan con error**
  (no se reasignan).

## 2. Subtareas

### 17.1 Contratos

**Nuevo enum** (cerrado, minúsculas):

| Enum | Valores |
| :--- | :--- |
| `KBEntryType` | `finding` (único por ahora; el archivo queda extensible) |

**Formato del archivo de export** (JSON, UTF-8, indentado 2, en
`metatracer/knowledge/portable.py`):

```json
{
  "format_version": 1,
  "kb_name": "MetaTracer knowledge base export",
  "exported_at": "2026-09-13T20:30:00Z",
  "entries": [
    {
      "finding_id": "<uuid4>",
      "finding_type": "gps",
      "evidence_snippet": "Latitude: 40.4168, Longitude: -3.7038",
      "severity": "high",
      "title": null,
      "created_at": "2026-09-11T10:00:00Z"
    }
  ]
}
```

Campos de cada entrada (contrato cerrado; **no** incluir `run_id`), alineados
con `RetrievedEvidence` y con el seed del FTS5 (TASK-14.14.1):
`finding_id`, `finding_type`, `evidence_snippet` (sanitizado, sin bytes),
`severity` (nullable), `title` (nullable), `created_at`.

`severity` puede ser `null` (findings sin clasificar) — se preserva tal cual.

**Nada más sale del archivo**: ni `run_id`, ni `asset_id`, ni `field_source`,
ni `dedup_signature`, ni `source_url`, ni `agent_model_used`, ni `scan` de
reproducción, ni metadata cruda, ni bytes.

### 17.2 Módulo `metatracer/knowledge/portable.py`

Nuevo paquete `metatracer/knowledge/` (junto a `agents/`), **0 dependencias
nuevas** (stdlib `json`/`datetime`):

- `class KBEntryType(StrEnum)` — cerrado, `finding`.
- `@dataclass KBEntry` — `finding_id`, `finding_type`, `evidence_snippet`,
  `severity: Severity | None`, `title: str | None`, `created_at: datetime | None`.
- `async def export_kb(session_factory, dest: Path, *, limit: int = 1000) -> int`:
  - Lee los `_INDEX_SEED_LIMIT` (1000) **findings más recientes** por
    `created_at` (mismo seed que `KnowledgeIndex.rebuild`, TASK-14).
  - Escribe el JSON portable al `dest` con `format_version`,
    `kb_name`, `exported_at` (UTC ISO) y `entries`.
  - Devuelve el nº de entradas; si no hay findings, escribe un archivo con
    `entries: []` (válido, no error).
  - ~1000 filas sobre el archivo local: operación barata.
- `async def import_kb(session_factory, source: Path) -> int`:
  - Lee el JSON, valida `format_version == 1` y estructura (lista `entries`).
  - Construye `KBEntry` validando `finding_type` y `severity` contra los enums
    cerrados; un valor inválido → **`ValueError` con detalle** (p. ej.
    `invalid entry 3: unknown finding_type 'bogus'`) — no se reasigna.
  - Para cada entrada `finding`, **inserta un `Finding`** con:
    - `id = entry.finding_id` si no existe (ver `_finding_exists` para
      idempotencia), `run_id` y `asset_id` **nuevos** (UUID4) — el import
      crea un run/asset "sombra" para satisfacer FK sin arrastrar el run
      original;
    - `finding_type`, `evidence_snippet`, `severity`, `title` desde el entry;
    - `field_source = "kb-import"`, `detector_method = "heuristic"`,
      `confidence = "medium"`, `dedup_signature` **nuevo** basado en
      `asset_id` (el import es idempotente y no arrastra los IDs de origen);
    - `created_at` del entry (si lo trae) o `_utc_now()`.
  - **Idempotente**: si ya existe un `Finding` con ese `finding_id`, lo omite
    (no duplica). Devuelve el nº de filas insertadas.
  - **No borra nada** y no toca el índice FTS5 (se reconstruye lazy en el
    próximo run / `rebuild`).
  - Un `source` con `format_version` desconocido o estructura inválida →
    `ValueError` descriptivo.

Helpers:
- `_finding_exists(session, finding_id) -> bool` — consulta por PK.
- `_write_json(path, payload)` / `_read_json(path)` — escriben/leen con
  encoding UTF-8 y `ensure_ascii=False`.

### 17.3 Cambios `metatracer/agents/knowledge.py`

- `KnowledgeIndex.rebuild()` reordena la carga de filas para **reusar el mismo
  seed** que el export: `_load_seed_findings` (mismas columnas) — sin cambios
  de contrato.

### 17.4 CLI (`metatracer/cli/main.py`)

Dos subcomandos nuevos bajo el grupo `kb` (Typer, alineado con la CLI
existente):

- `metatracer kb export --output <path> [--limit <n>]`: llama a `export_kb`,
  imprime con Rich cuántas entradas se exportaron y a qué archivo. Default
  `--output kb-export.json`, `--limit 1000`.
- `metatracer kb import --input <path>`: valida y llama a `import_kb`, imprime
  cuántas entradas se importaron. Sin output → error claro.

No añadir dependencias (Typer/Rich ya están).

### 17.5 API (`metatracer/api/knowledge.py` o nuevo router `portable`)

- `POST /api/knowledge/export` → ejecuta el export a un archivo temporal y lo
  devuelve como `FileResponse` (application/json, `.json`) → **el operador lo
  descarga**; NO lo guarda en el servidor.
- `POST /api/knowledge/import` → acepta el archivo subido
  (UploadFile), lo escribe a temp y llama a `import_kb`; responde
  `{"imported": <n>}`.
- **Sin diálogo de confirmación en BD ni borrado**: el import inserta; el
  usuario puede revertir con un `DELETE` si se equivoca (no implementado en
  esta task).
- Endpoint read-only del índice (TASK-14) **no cambia**.

Patrón de wiring en `app.py`: igual que `knowledge_retriever`; en los nuevos
endpoints se usa `request.app.state.session_factory`.

### 17.6 Safety y persistencia

- Los `finding_id` del archivo son estables (para idempotencia del import),
  pero **no** son del run de origen (se generan nuevos al importar si hiciera
  falta; el formato los trae para que el mismo archivo importado dos veces no
  duplique).
- El export NO incluye `run_id` ni metadata cruda: es el corpus de
  precedentes, no el dump de la BD.
- El import NO borra nada; solo inserta / omite duplicados.
- El RAG nunca exporta snippets de otros runs fuera de la máquina vía
  webhook/reporte (invariante ya fijada en TASK-14 y TASK-15); la KB portable
  es el único canal de egreso de ese corpus y va **por archivo local elegido
  por el operador**.

---

## 3. Fuera de alcance

- Encriptación/firma del archivo (el operador lo mueve por canales que él
  controle; el MVP asume archivo local).
- Formatos no-JSON (gzip, ZIP, SQLite dump).
- Import selectivo por `finding_type` o por rango de fechas (se trae todo).
- Sincronización bidireccional / merge con conflictos.
- Migración entre `format_version`s: solo se soporta la 1.
- Export/import de feedback (`finding_feedback`) o del índice FTS5 en crudo.

---

## 4. Tests mínimos

- `tests/unit/test_kb_portable.py`:
  - `export_kb` escribe JSON con `format_version`, `kb_name`, `exported_at`
    y `entries` con las claves del contrato; ~ N findings exportados.
  - `export_kb` no incluye `run_id`/`asset_id`/`field_source`/`dedup_signature`
    ni metadata cruda en las entradas.
  - `export_kb` sin findings → `entries: []` válido, devuelve 0.
  - `import_kb` inserta `Finding`s correctos con FK a un run/asset sombra
    nuevos; idempotente (re-importa sin duplicar).
  - `import_kb` rechaza `format_version` desconocido y `finding_type`/`severity`
    inválidos con `ValueError` (no reasigna).
- `tests/integration/test_api_kb_portable.py`:
  - `POST /api/knowledge/export` devuelve JSON descargable con las entradas.
  - `POST /api/knowledge/import` con un archivo válido inserta filas y responde
    `{"imported": n}`.
  - El import re-importado no duplica (idempotencia a través de la API).
  - Sin archivo → 422.
- Suite completa en verde: `pytest -m "not e2e"` y `ruff check src tests`.
  (El guardrail de TASK-16 ya no es manual: se valida con `ci-check.ps1`.)

---

## 5. Criterios de aceptación (DoD)

- [x] Un operador exporta la KB a `kb-export.json` con `metatracer kb export`
      y el JSON contiene solo las claves del contrato (sin `run_id` ni
      metadata cruda).
- [x] Desde una BD vacía (o una máquina nueva), `metatracer kb import` del
      mismo archivo puebla la BD y el agente recupera esos precedentes en un
      run (el índice se reconstruye lazy).
- [x] Importar el mismo archivo dos veces no duplica filas (idempotencia por
      `finding_id`).
- [x] Import con `finding_type`/`severity` inválidos o `format_version`
      desconocido → error claro (no se reasigna).
- [x] Cero dependencias nuevas; cero red; cero bytes de archivos en el
      archivo JSON (solo snippets).
- [x] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio,
      validado con el guardrail de TASK-16 (`scripts/ci-check.ps1`).

## 6. Bugs heredados corregidos (TASK-14)

- **Doble sanitización del FTS**: el `KnowledgeRetriever` pre-sanitizaba el
  snippet y `KnowledgeIndex.search` lo re-sanitizaba, introduciendo `"AND"`
  como token literal → los precedentes nunca se recuperaban. Ahora el
  retriever pasa el snippet crudo y `search` sanitiza una sola vez. Test de
  regresión: `test_retrieve_no_double_sanitization_regression`.
- **Recuperación de precedentes importados**: el retriever añadía
  `field_source` a la query, pero los precedentes importados llevan
  `field_source='kb-import'` → quedaban irrecuperables. La query se construye
  ahora solo desde el snippet (fuente-independiente); `finding_type` sigue
  siendo post-filter del índice.