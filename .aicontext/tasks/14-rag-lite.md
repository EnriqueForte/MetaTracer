# TASK-14: RAG ligero con SQLite FTS5 (v2.1+)

**Módulo:** Inteligencia avanzada — recuperación de contexto histórico
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Agentes de IA](../features/05-ai-agents.md)
**Dependencias:** TASK-00 … TASK-13 (v1.0–v2.1), fase v2.1+
**Estado:** En curso

---

## 1. Objetivo técnico

Segundo slice de la fase **v2.1+ Inteligencia avanzada**. Hoy el agente (TASK-05)
analiza cada finding con solo el payload del run actual (`ContextOptimizer`) más
los ejemplos de feedback del mismo `finding_type` (TASK-13). Cuando un operador
ha trabajado el mismo tipo de objetivo antes (p. ej. "esta app de conserjería
filtra rutas internas en la 1.4.2"), ese aprendizaje vive en los rows de
`finding`/`finding_feedback`/`agent_log` de runs previos, pero no llega al
prompt: cada run empieza de cero.

El **RAG ligero** construye un índice **full-text (SQLite FTS5)** sobre los
hallazgos históricos y recupera los **más similares** (por coincidencia léxica
con el finding actual) para inyectarlos como contexto **externo y no
autoritativo** en el análisis del agente. El hallazgo actual sigue siendo la
fuente de verdad; los recuperados son pistas de "esto ya lo vi antes".

Qué aporta de producto:

- El agente recuerda cómo se resolvieron hallazgos iguales o parecidos en runs
  anteriores y puede anclar su explicación en precedentes reales (no en su
  memoria de entrenamiento ni en hechos inventados).
- **0 dependencias nuevas**, **0 migración de BD**: FTS5 es un módulo del
  propio SQLite, se indexa sobre las tablas existentes y el índice se
  reconstruye bajo demanda.
- Preparación para **PostgreSQL + pgvector** después: la capa de recuperación
  queda detrás de una interfaz (`KnowledgeRetriever`), de modo que un futuro
  `PgVectorRetriever` sustituya al `Fts5Retriever` sin tocar el grafo.

## 2. Subtareas

### 14.1 Contratos

No se añaden enums ni columnas. Se introduce un **modelo de contexto
recuperado** (dataclass de solo lectura, no persistido):

```
class RetrievedEvidence:
    finding_id: str
    run_id: str
    finding_type: FindingType
    evidence_snippet: str        # texto de evidencia, ya sanitizado (~150 chars)
    severity: Severity | None    # severidad final del finding (post-clasificación)
    title: str | None            # título agent-drafted, si existe
    created_at: datetime
    score: float                 # puntuación FTS5 (bm25/rank)
```

El índice FTS5 es un **artefacto derivado, no un modelo**: se borra y
reconstruye; nunca es fuente de verdad. No se añade a los contratos de enums.

Actualizar antes: `.aicontext/tasks/README.md` (tabla de tasks + slice) y el
skill de contratos si procede.

### 14.2 Índice FTS5 (`KnowledgeIndex`)

Nuevo módulo `metatracer/agents/knowledge.py` (sin dependencias fuera del
stack actual — FTS5 viene con SQLite):

- `class KnowledgeIndex`:
  - `__init__(self, engine, session_factory)`
  - `async def rebuild(self) -> None`: crea el **índice FTS5 virtual** y lo
    rellena con los `Finding` históricos (los `_INDEX_SEED_LIMIT=1000` más
    recientes, por `created_at`): fila con `finding_id`, `run_id`,
    `finding_type`, `evidence_snippet`, `field_source`, `severity`, `title`,
    `created_at`. La tabla virtual vive en el mismo archivo SQLite.
  - `async def search(self, query, *, finding_type=None, exclude_finding_id=None, limit=5) -> list[RetrievedEvidence]`:
    consulta FTS5 con `MATCH` + `ORDER BY rank`, filtra por `finding_type`
    y `exclude_finding_id` (post-filtros en Python), devuelve los `limit`
    top con su `score`. La query se sanitiza a tokens alfanuméricos unidos
    con `AND` (los snippets llevan `.` `/` `@` que romperían FTS5).
- `class KnowledgeRetriever(engine, session_factory, *, limit=5)`:
  - `async def retrieve(payload, *, exclude_finding_id=None) -> list[RetrievedEvidence]`:
    construye la query desde el payload cerrado (`evidence_snippet` +
    `field_source` + `finding_type`), sin red y sin texto libre del operador.
- El corpus es **solo findings** (no feedback) en este slice: los ejemplos del
  operador ya viajan por el canal `feedback_examples` de TASK-13 y no deben
  duplicarse como hit histórico.

### 14.3 Recuperador (`KnowledgeRetriever`)

`metatracer/agents/knowledge.py` (mismo módulo):

```
class KnowledgeRetriever:
    '''Recupera contexto histórico para un finding (RAG ligero, TASK-14).'''

    def __init__(self, engine, session_factory, *, limit=5) -> None
    async def retrieve(
        self, payload: dict[str, str], *, exclude_finding_id: str | None = None
    ) -> list[RetrievedEvidence]:
        '''Retorna los findings históricos más similares al payload.

        La query FTS5 se construye desde los campos del payload (evidence
        snippet + finding_type + field_source), NO desde texto libre del
        operador. Nunca toca red.
        '''
```

- `retrieve` construye la query con `evidence_snippet` (y `field_source`),
  opcionalmente restringida por `finding_type`. Si no hay índice o está vacío
  devuelve `[]` (no-op).
- **Invariante**: este módulo **no hace ninguna llamada de red**, no lee
  archivos, no toca la BD del run actual más allá del índice. Solo texto del
  payload → resultados del índice.

### 14.4 Inyección en el grafo del agente

Reutilizar el **mismo canal** que TASK-13 (`feedback_examples`): el contexto
recuperado viaja **fuera** del payload cerrado de `ContextOptimizer`, como clave
adicional `retrieved_evidence` en `entry` (no dentro de `payload`).

- En `AgentPipeline.execute`: si hay `retriever` inyectado, para cada finding
  optimizado llamar `retriever.retrieve(payload, exclude_finding_id=finding.id)`
  y adjuntar `entry["retrieved_evidence"]` (lista de `RetrievedEvidence`).
- En `AnalyzeContextNode`: si `entry` trae `retrieved_evidence`, fusionarlo en
  `model_payload` como `retrieved_evidence` (guía no autoritativa; el prompt le
  dice al modelo que cite solo el payload y trate lo recuperado como contexto
  adicional verificable). **Nunca** deja que el contexto recuperado aparezca
  como evidencia del finding actual.
- El `ContextOptimizer` no cambia: el payload cerrado sigue intacto; lo
  recuperado viaja en paralelo como `entry["retrieved_evidence"]`.

### 14.5 Guard y trazabilidad

- `EvidenceGuard` **no** se relaja: la rúbrica y el payload siguen siendo
  autoridad. El contexto recuperado es solo contexto de análisis; si el modelo
  lo cita, debe ser como precedente, no como evidencia nueva.
- Añadir en `AgentLog` (via `guard_notes` o campo del log) una nota
  `retrieved_evidence_used=<n>` cuando se inyectaron documentos recuperados,
  para trazabilidad.

### 14.6 API/CLI (opcional, barato)

- `GET /api/knowledge/search?q=<query>&finding_type=<type>&limit=5` — endpoint de
  inspección del índice (para demo y depuración). **Read-only**, sin red.
- En CLI: no añadir nueva subcomandos en este slice (se puede exponer en la
  demo vía API). El `rebuild` se puede forzar con un flag de debug si el
  pipeline no lo hace lazy.

### 14.7 Safety y persistencia

- **Cero bytes de archivos**: el índice solo guarda snippets de texto ya
  presentes en las tablas; nunca bytes ni el archivo.
- **Sin red nueva**: el RAG es **100% local**. No hay llamadas a un servicio de
  embeddings, no hay índice remoto, no hay datos que abandonen la máquina.
- **La evidencia de otros runs es sensible**: el índice vive en la BD local
  (`.gitignore`), no se exporta en reportes ni en la API fuera del endpoint de
  inspección (que está detrás del mismo server local).
- **Privacidad de datos personales**: los snippets recuperados son de otros
  findings (p. ej. coordenadas GPS); solo viajan al prompt del agente para el
  **mismo operador** en su máquina. No se loguean; en `AgentLog` solo se guarda
  el contador, no los snippets.

---

## 3. Fuera de alcance

- Embeddings semánticos / pgvector / modelos de embeddings remotos (futuro
  cuando haya PostgreSQL).
- RAG sobre documentos externos (PDFs/URLs arbitratios) — MetaTracer no ingiere
  documentación corporativa.
- Indexado automático incremental (cada run reconstruye si toca; sin
  triggers/eventos).
- Exposición del índice en reportes o dashboard.
- Multi-usuario / tenancy del índice (el índice es local al operador).

---

## 4. Tests mínimos

- `tests/unit/test_knowledge_index.py` — `rebuild` + `search` devuelve el top-N
  por rank; filtro por `finding_type`; excluye `exclude_finding_id`; índice
  vacío → `[]`.
- `tests/unit/test_knowledge_retriever.py` — `retrieve` construye la query desde
  el payload; sin índice → `[]` (no-op); respeta `limit`; los resultados son
  `RetrievedEvidence` con `score`.
- `tests/unit/test_knowledge_injection.py` (o en pipeline) — `AgentPipeline`
  adjunta `retrieved_evidence` a `entry` solo si hay retriever; `AnalyzeContextNode`
  fusiona `retrieved_evidence` en `model_payload` sin tocar `payload`.
- `tests/integration/test_knowledge_api.py` — `GET /api/knowledge/search`
  read-only: sin escrituras; 422 sin `q`; devuelve resultados con índice poblado.
- Suite completa en verde: `pytest -m "not e2e"` y `ruff check src tests`.

---

## 5. Criterios de aceptación (DoD)

- [x] Con findings históricos (runs previos) en la BD, un run nuevo con agentes
      inyecta `retrieved_evidence` en el prompt del agente (trazable en
      `AgentLog.raw_response` via `guard_notes`).
- [x] El finding actual queda excluido de sus propios resultados.
- [x] `retrieved_evidence` **nunca** sustituye a `payload.evidence_snippet` ni
      altera `finding_type`/`severity` del finding actual.
- [x] Sin hallazgos históricos o sin LLM configurado: el pipeline se comporta
      exactamente igual que v2.1 sin RAG (no-op).
- [x] Cero dependencias nuevas; indexado sobre tablas existentes sin migración.
- [x] Cero red: el RAG no llama a ningún servicio; todo es local.
- [x] `pytest -m "not e2e"` en verde (418 passed) y `ruff check src tests` limpio.