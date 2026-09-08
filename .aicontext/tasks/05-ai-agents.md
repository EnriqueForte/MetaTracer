# TASK-05: Agentes de IA y Orquestación con LangGraph

**Módulo:** Agentes de IA  
**Referencia PRD:** [Agentes de IA](../features/05-ai-agents.md)  
**Dependencias:** [TASK-02](02-specific-detection.md), [TASK-03](03-risk-classification.md)  
**Estado:** Completada  

> Implementación en `src/metatracer/agents/`: `optimizer` (ContextOptimizer, payload cerrado de 8 claves, presupuesto ~1.500 tokens, recorte por `max_assets_per_run` con prioridad por tipo), `schemas` (structured output, `extra="forbid"`, sin `finding_type`/`evidence_snippet` para que el modelo no pueda mutar evidencia), `guard` (EvidenceGuard post-LLM: cita substring, techos de rúbrica + severidad soportada por el snippet, filtro de palabras-payload), `llm` (routing fuerte/rápido con ChatOpenAI, tenacity 3 intentos, `max_tokens` de salida contra denial-of-wallet, `NullAgentClient` sin clave), `graph` (AgentState + 6 nodos, persistencia inyectada vía `EvaluationWriter`), `pipeline` (`AgentPipeline.execute(run_id)`, escritor SQL, una fila `AgentLog` por finding, nunca el prompt). Prompts versionados en `agents/prompts/` con `RUBRIC_PROMPT_TEXT` inyectada. Tests en `tests/agents/` (41 tests, stubs de chat model, sin red real). Decisión de supply chain: `langchain-openai>=1.0` aprobada y registrada en TASK-00 (0.1.3).

---

## 1. Objetivo Técnico

Grafo LangGraph que, sobre findings ya detectados (y normalmente ya baselineados por el heurístico): analiza contexto, ajusta severidad según la rúbrica, y redacta explicación / impacto / remediación / repro.

Optimización de contexto obligatoria: **cero binarios**. Si el LLM no está o falla, fallback al heurístico de TASK-03 **sin perder findings**.

---

## 2. Subtareas Detalladas

### Subtarea 5.1: `ContextOptimizer`

- **5.1.1. Payload máximo por finding** (y nada más):

  ```json
  {
    "finding_type": "internal_path",
    "field_source": "XMP:CreatorTool",
    "evidence_snippet": "C:\\Users\\admin\\Projects\\Internal\\doc.pdf",
    "confidence": "high",
    "heuristic_severity": "high",
    "target_domain": "target.com",
    "asset_content_type": "application/pdf",
    "asset_url": "https://target.com/doc.pdf"
  }
  ```

  Prohibido: bytes, EXIF completo, dump de todos los `RawMetadataItem`, HTML, thumbnails.

- **5.1.2.** Tirar keys vacías y valores de plantilla nulos.
- **5.1.3.** Agrupar por asset o tipo solo si no mezcla evidencias. Tope de ~1.500 tokens por llamada (estimar con `len(text)//4` es aceptable en el MVP).
- **5.1.4. Tope de coste:** no enviar más de `MAX_ASSETS_PER_RUN` findings de más; si hay un número absurdo, priorizar por tipo (gps, internal_path, debug_comment, email, software_version) y loguear el recorte.

---

### Subtarea 5.2: Esquemas y modelos

- **5.2.1.** Enums Pydantic en **minúsculas** (mismo contrato que TASK-00).

  ```python
  class AgentFindingEvaluation(BaseModel):
      severity: SeverityEnum
      justification: str
      impact_analysis: str
      remediation: str
      reproduction_steps: list[str]
      cited_evidence: str
      title: str
  ```

  Usar `with_structured_output` / tool calling. Si el modelo no cumple el schema, reintento una vez y luego fallback.

- **5.2.2. Routing:**
  - Modelo fuerte (`LLM_MODEL`, Kimi/Moonshot vía API compatible OpenAI): análisis + severidad.
  - Modelo rápido (`FAST_MODEL`): títulos y summary ejecutivo.
  - Cliente: LangChain ChatOpenAI o equivalente apuntando a `LLM_BASE_URL` + `LLM_API_KEY`.
  - Prompts en `src/metatracer/agents/prompts/` (archivos `.md` o `.txt` versionados). El system prompt **incluye la rúbrica de TASK-03** y las prohibiciones: no CVEs inventados, no exploits, no hechos fuera del payload, no subir GPS a `critical` sin texto extra en el snippet.

- **5.2.3. Invariantes que el validador post-LLM aplica:**
  - `cited_evidence` debe ser substring de `evidence_snippet` (casefold, whitespace colapsado permitido).
  - El modelo **no** puede cambiar `finding_type` ni `evidence_snippet`.
  - Si propone severity por encima del techo heurístico de TASK-03 sin que el snippet lo soporte, **desescalar** al techo.
  - `reproduction_steps` no pueden contener palabras de payload (`msfvenom`, `/etc/passwd` como receta de ataque, etc. — lista corta; el espíritu es inspección con `exiftool`/`pdfinfo`/`curl`).

---

### Subtarea 5.3: `MetaTracerGraph`

- **5.3.1. Estado:**

  ```python
  class AgentState(TypedDict):
      target_domain: str
      reasoning_depth: Literal["brief", "standard", "detailed"]
      raw_findings: list[dict]
      evaluated_findings: list[dict]
      current_index: int
      error_log: list[str]
  ```

- **5.3.2. Nodos:**
  - `AnalyzeContextNode` — triager de bounty; no asumir hechos no dados (p. ej. “es la casa del CEO”).
  - `ClassifySeverityNode` — rúbrica TASK-03 + validación de evidencia citada.
  - `DraftExplanationNode` — verbosidad:
    - `brief`: 1 párrafo
    - `standard` (default): 2–3 párrafos + remediación
    - `detailed`: más contexto ofensivo/defensivo **sin** recetas de exploit
  - `SaveFindingEvaluationNode` — persiste campos de prosa + `severity` + `agent_model_used` + `AgentLog`. También `Finding.title` cuando la evaluación no es fallback (el reporte lo usa como título de ficha).
  - `SynthesizeReportSummaryNode` — párrafo ejecutivo (modelo rápido). `AgentPipeline` lo persiste en `Run.executive_summary` para que TASK-04 lo consuma en cualquier export.

- **5.3.3. Topología:**

  ```text
  [START]
     │
     ▼
  [LoadNextFindingNode] ── no quedan ──► [SynthesizeReportSummaryNode] ──► [END]
     │
    sí
     ▼
  [AnalyzeContextNode] → [ClassifySeverityNode] → [DraftExplanationNode]
     │
     ▼
  [SaveFindingEvaluationNode] ──► LoadNextFindingNode
  ```

  Flujo de producto: detectar → analizar → clasificar → explicar → reportar. El grafo cubre analizar/clasificar/explicar.

---

### Subtarea 5.4: Resiliencia y fallback

- **5.4.1.** `tenacity`: 3 reintentos, backoff exponencial con jitter, sobre 429/500/timeout.
- **5.4.2.** Tras agotar reintentos, o si `LLM_API_KEY` está vacío: `HeuristicRiskClassifier`. `agent_model_used = "heuristic-fallback"`. El finding **no** se borra.
- **5.4.3.** Rate limit entre llamadas al LLM (conservador; 1 finding/llamada es aceptable en MVP).
- **5.4.4.** Si `reasoning_depth` cambia, solo cambia la prosa, no evidence ni tipo.

---

## 3. Fuera de alcance de esta tarea

- RAG, feedback loop, agentes que decidan el crawl (v2.1+ / nunca para scope).
- Generación de exploits o payloads.
- Enviar el archivo o el dump EXIF completo “para más contexto”.

---

## 4. Tests mínimos

- `tests/agents/test_context_optimizer.py` — el payload no contiene bytes ni keys binarias.
- `tests/agents/test_langgraph_flow.py` — LLM fake (`FakeListLLM` o responder con JSON fijo); el estado recorre todos los nodos; schema válido.
- `tests/agents/test_agent_fallback.py` — error 500/timeout/clave vacía → heurístico, run no aborta.
- `tests/agents/test_evidence_guard.py` — `cited_evidence` alucinada → rechazo o downgrade; GPS a `critical` sin texto extra → cap `high`.

No llamar APIs reales en CI.

---

## 5. Criterios de Aceptación (DoD)

- [x] El grafo recorre una lista de findings y persiste evaluaciones schema-válidas.
- [x] Ninguna petición al modelo incluye bytes de archivo.
- [x] El agente no inventa coordenadas/rutas/emails ausentes del snippet.
- [x] `brief` / `standard` / `detailed` cambian la longitud de la prosa, no la evidencia.
- [x] LLM caído o sin API key → fallback heurístico, scan global continúa.
- [x] `agent_model_used` queda relleno (modelo real o `heuristic-fallback`).
