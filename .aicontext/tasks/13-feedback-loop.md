# TASK-13: Feedback loop (v2.1+)

**Módulo:** Inteligencia avanzada — aprendizaje por corrección humana
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Agentes de IA](../features/05-ai-agents.md)
**Dependencias:** TASK-00 … TASK-12 (v1.0–v2.0 cerradas), fase v2.1+
**Estado:** Completada

---

## 1. Objetivo técnico

Primer slice de la fase **v2.1+ Inteligencia avanzada**. Hoy el clasificador
heurístico (TASK-03) y el agente (TASK-05) asignan severidad **una sola vez**:
cuando el operador — que tiene el contexto del engagement — corrige esa
severidad (p. ej. *"este GPS es de la sede pública, no `high`"*), la corrección
se pierde y el siguiente run repite el mismo error.

El **feedback loop** convierte esa corrección humana en **memoria de pocos
ejemplos (few-shot)**: cada corrección aceptada se persiste en una tabla nueva
`finding_feedback` y se reinyecta como ejemplo guía en el prompt de
clasificación/agente de runs futuros con hallazgos similares (mismo
`finding_type`). El agente aprende del contexto del operador **sin cambiar
reglas hard-coded** y **sin relajar el guard anti-alucinación**.

Qué aporta de producto:

- El operador corrige la severidad de un finding desde la Web UI y esa
  corrección **persiste** (no se pierde al cerrar el run).
- Los runs siguientes **mejoran la primera impresión**: el agente/heurístico
  ve ejemplos reales previos del mismo tipo antes de proponer severidad.
- La decisión final sigue siendo del guard (`EvidenceGuard`) y de la rúbrica:
  el feedback **nunca inventa severidad** por sí mismo, solo la sugiere.

---

## 2. Subtareas

### 13.1 Contratos

Nuevo enum `FeedbackVote` (en `metatracer.db.models`):

| Valor | Significado |
| :--- | :--- |
| `up` | El operador considera que la severidad era **baja** (debería subir) |
| `down` | El operador considera que la severidad era **alta** (debería bajar) |

Nuevo modelo `FindingFeedback` (en `metatracer.db.models`), sin tocar los demás:

| Columna | Tipo | Restricciones |
| :--- | :--- | :--- |
| `id` | `str` UUID4, PK | como las demás entidades |
| `finding_id` | `str` FK → `finding.id` | **indexed** |
| `run_id` | `str` FK → `run.id` | indexed |
| `vote` | `FeedbackVote` | `up` \| `down` |
| `severity_before` | `Severity` | la severidad que tenía el finding al votar |
| `severity_after` | `Severity` | la severidad corregida (que el operador propone) |
| `reason` | `str \| None` | Text opcional, por qué (contexto del engagement; **nunca** evidencia nueva) |
| `created_at` | `DateTime(timezone=True)` | UTC, default `_utc_now()` |

Reglas de dominio:

- `vote=up` → `severity_after` es **mayor** que `severity_before` en el orden
  `info → low → medium → high → critical`.
- `vote=down` → `severity_after` es **menor** que `severity_before`.
- Un `severity_after == severity_before` **se rechaza** (422): no hay corrección.
- `reason` se trunca a **~150 chars** al persistir (igual que snippets;
  defensa de profundidad contra ruido en el prompt).
- **Un finding admite un solo feedback activo por `finding_id`**: si ya existe
  uno, `PUT /api/feedback` lo **reemplaza** (update), no crea duplicados. Esto
  mantiene la memoria acotada y evita que un finding spammee ejemplos.

Actualizar **antes** de persistir valores nuevos: `.aicontext/tasks/README.md`
(tabla de tasks) y el [skill de contratos](../../.cursor/skills/metatracer-data-contracts/SKILL.md).

### 13.2 Modelo y repositorio

- Definir `FeedbackVote` y `FindingFeedback` en `metatracer/db/models.py`.
- `FeedbackRepository` en `metatracer/db/repositories.py`:
  - `create(feedback)`, `get_by_finding(finding_id)`, `upsert_by_finding(feedback)`,
    `list_recent(limit=...)` (para el re-populate del memory), `delete(finding_id)`.
  - `upsert_by_finding` = update si ya hay feedback para ese `finding_id`, si no
    insert (evita duplicados y respeta la regla "un feedback por finding").
- **Intentar añadir la tabla con el mecanismo existente** de `init_db`
  (`create_all` + `_add_missing_nullable_columns`). Tabla nueva se crea sola;
  no requiere migración. Si aparece un caso que requiera migración real,
  documentarlo en un ADR antes de tocar nada (Alembic sigue **fuera de alcance**).

### 13.3 Memoria de pocos ejemplos (`FeedbackMemory`)

Nuevo módulo `metatracer/agents/memory.py` (sin dependencias fuera del stack
actual; **cero dependencias nuevas**):

```
class FeedbackExample(BaseModel):
    finding_type: FindingType
    evidence_snippet: str        # ~150 chars, sanitized
    field_source: str
    severity_before: Severity
    severity_after: Severity
    vote: FeedbackVote

class FeedbackMemory:
    '''Few-shot memory over persisted FindingFeedback rows.'''

    def __init__(self, max_examples_per_type: int = 5) -> None
    async def load(self, session) -> None   # carga feedback reciente con su finding
    def examples_for(self, finding_type: FindingType) -> list[FeedbackExample]
```

- `load` consulta `FeedbackRepository.list_recent(limit=N)` y une con el
  `Finding` para obtener `finding_type`/`evidence_snippet`/`field_source`/`severity`.
- `examples_for(type)` devuelve **solo** ejemplos de ese `finding_type`,
  acotados a `max_examples_per_type` (los más recientes), nunca evidencia de
  otro tipo (evita contaminación cross-type).
- **Nunca incluye `reason` del operador en el prompt**: el `reason` puede
  contener contexto sensible del engagement; el ejemplo solo lleva
  `severity_before`/`severity_after` + `vote` + campos del finding ya
  presentes en el payload. (Invariante: el LLM nunca ve texto libre del
  operador que no sea el snippet estructurado.)
- `FeedbackMemory` se inyecta en `AgentPipeline` y en `ClassificationPipeline`
  (parámetros opcionales con default), igual que `notifications` en el
  orquestador: una memoria vacía es **no-op** y el pipeline funciona igual.

### 13.4 Inyección en clasificación (heurístico + agente)

Reutilizar el canal **existente** sin crear uno nuevo: el feedback se inyecta
como **few-shot examples en el prompt del agente** y como **contexto en el
clasificador heurístico** (que ya es la fuente de verdad de fallback y reporte).

- En `AgentPipeline.execute`: tras cargar `optimized`, si `memory.examples_for(type)`
  no está vacío, añadir a `entry["payload"]` una clave `feedback_examples` con
  los ejemplos serializados (sin `reason`, sin campos extra) — el `ContextOptimizer`
  ya descarta claves vacías, así que ausencia de feedback = payload sin cambios.
- En `ClassificationPipeline.execute`: al clasificar un finding, pasar
  `examples_for(finding.finding_type)` al `HeuristicRiskClassifier.classify`
  (nuevo parámetro opcional `feedback_examples=()`). Si hay ejemplos, el
  clasificador **puede sesgar** la severidad hacia `severity_after` más votada
  del tipo **solo como baseline adicional**, manteniendo el tope de GPS y las
  plantillas por tipo como fuente de verdad. Sin ejemplos → comportamiento
  idéntico al actual.
- El guard (`EvidenceGuard`) sigue aplicando después: el feedback es una
  **sugerencia**, la rúbrica y el guard siguen siendo autoridad. Añadir la nota
  `"operator feedback example applied"` en `guard_notes` cuando se usó un ejemplo
  (para trazabilidad en `AgentLog`).

Regla dura: **el feedback nunca modifica `evidence_snippet` ni `finding_type`**
del finding — solo puede influir la severidad propuesta.

### 13.5 API

Nuevo router `metatracer/api/feedback.py` (prefix `/api/feedback`, tag
`feedback`):

| Método | Ruta | Código | Comportamiento |
| :--- | :--- | :--- | :--- |
| `PUT` | `/api/feedback/{finding_id}` | 200 / 404 / 422 | Crear o reemplazar el feedback del finding |
| `GET` | `/api/feedback/{finding_id}` | 200 / 404 | Consultar el feedback activo de un finding |
| `DELETE` | `/api/feedback/{finding_id}` | 204 / 404 | Borrar el feedback (memoria se vacía para ese finding) |

- `FeedbackCreate` en `api/schemas.py` (o junto al router):
  - `vote: FeedbackVote`
  - `severity_after: Severity` (obligatorio)
  - `reason: str | None` (opcional, strip, trunca a ~150 chars)
- Validación: `severity_after` debe ser **distinta** y **en la dirección** del
  `vote` respecto a la severidad actual del finding. El 404 → `finding not found`; 
  el 422 → `vote/severity mismatch`.
- El router es **solo lectura de datos + escritura de feedback** (sin red, sin
  scope): el feedback se asocia a un finding ya persistido, nunca dispara
  llamadas externas.
- Registro en `api/app.py` (junto a los demás routers).

### 13.6 Web UI

- `run.html` (o el detalle de finding): cada finding muestra el **estado de
  feedback** — `up` / `down` / ninguno — y dos controles: "subir severidad"
  (`vote=up`) y "bajar severidad" (`vote=down`), con un campo opcional de
  `reason`.
- Envío por `fetch` a `PUT /api/feedback/{finding_id}`; render del estado con
  `x-text` (nunca `x-html`), manteniendo el patrón Alpine de la app.
- Tras enviar, el botón pasa a estado "activo"; re-envío = reemplazo (update).
- Sin dependencias nuevas.

### 13.7 Safety y persistencia

- **Cero bytes de archivos** (solo texto corto).
- **Cero rastro de secretos**: `reason` se sanitiza con `sanitize_for_log` antes
  de cualquier log, y **nunca** viaja al LLM.
- **No relajar** el gate de scope ni el guard: el feedback solo sugiere
  severidad, nunca autoriza red fuera de scope ni inventa evidencia.
- El `FindingFeedback` es una tabla **local** del operador: no se exporta a los
  reportes (los reportes de bounty no deben contener anotaciones internas del
  equipo). El dashboard podría agregarlo en un slice futuro, queda **fuera de
  alcance**.

---

## 3. Fuera de alcance

- RAG vectorial / pgvector / PostgreSQL (siguiente slice de v2.1+, aún sin
  decidir BD).
- Integraciones con plataformas de bounty / webhooks / Slack (indefinido).
- Feedback que modifique `evidence_snippet`, `finding_type` o reglas hard-coded.
- Aprendizaje que se auto-alimente (feedback de feedback), métricas de
  exactitud por operador, multi-usuario/autenticación.
- Exportar feedback a reportes, dashboard agregado de feedback.
- Migración real de BD / Alembic; `run.feedback_id` FK.

---

## 4. Tests mínimos

- `tests/unit/test_feedback_repository.py` — CRUD + `upsert_by_finding`
  (crear, reemplazar, borrar); `get_by_finding` devuelve `None` si no existe.
- `tests/unit/test_feedback_memory.py` — `load` + `examples_for` filtra por
  `finding_type` y limita a `max_examples_per_type`; sin `reason` en los
  ejemplos; memoria vacía → no-op.
- `tests/unit/test_feedback_classifier_injection.py` — el clasificador con
  `feedback_examples` produce severidad distinta/igual respetando tope de GPS;
  sin ejemplos → idéntico al actual.
- `tests/integration/test_api_feedback.py` — PUT crea/actualiza, GET devuelve,
  DELETE 204/404; 422 con `severity_after == severity_before` y con
  `vote/severity` contradictorios; 404 finding inexistente; **GET es
  read-only**.
- `tests/integration/test_feedback_page.py` — `/runs/{run_id}` contiene los
  controles de feedback sin requerir datos sembrados.
- Suite completa en verde: `pytest -m "not e2e"` y `ruff check src tests`.

---

## 5. Criterios de aceptación (DoD)

- [x] Un operador puede corregir la severidad de un finding vía `PUT /api/feedback`
      y la corrección persiste (`GET` la devuelve).
- [x] Corregir el mismo finding dos veces reemplaza (no duplica) el feedback.
- [x] Con feedback existente del mismo `finding_type`, un run nuevo sugiere
      severidad acorde a los ejemplos (el heurístico lo refleja y el agente lo
      ve en el prompt), **sin** tocar `evidence_snippet` ni `finding_type`.
- [x] El feedback nunca viaja al reporte ni al LLM como texto libre (`reason`
      queda fuera del prompt).
- [x] Una memoria vacía deja el pipeline idéntico al de v2.0 (no-op total).
- [x] Cero dependencias nuevas; la tabla `finding_feedback` se crea con
      `create_all` (sin migración real).
- [x] Cero relajación del safety gate/guard; sin red nueva en feedback.
- [x] `pytest -m "not e2e"` en verde (403 passed) y `ruff check src tests` limpio.