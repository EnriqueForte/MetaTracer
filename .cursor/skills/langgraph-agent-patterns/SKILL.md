---
name: langgraph-agent-patterns
description: Grafo LangGraph de MetaTracer, ContextOptimizer (payload cerrado y presupuesto de tokens), structured output, routing de modelos fuerte/rápido, reintentos con tenacity, guard post-LLM y fallback heurístico. Usar al tocar src/metatracer/agents/ (graph.py, pipeline.py, optimizer.py, guard.py, llm.py, schemas.py, memory.py, knowledge.py) o los prompts de agents/prompts/.
---

# Agente LangGraph

El grafo **enriquece** findings ya persistidos; no orquesta el scan.
Fuente: `.aicontext/tasks/05-ai-agents.md`.

## Topología (`graph.py`)

```
START → LoadNextFinding ─(quedan findings)─→ AnalyzeContext
                                                 ↓
                                          ClassifySeverity   (EvidenceGuard)
                                                 ↓
                                          DraftExplanation   (título rápido + depth)
                                                 ↓
                                          SaveEvaluation ──→ loop a LoadNextFinding
      LoadNextFinding ─(no quedan)─→ SynthesizeReportSummary → END
```

- Nodos: `load_next_finding`, `analyze_context`, `classify_severity`,
  `draft_explanation`, `save_evaluation`, `synthesize_summary`.
- **Persistencia fuera del grafo**: `SaveFindingEvaluationNode` delega en un
  `EvaluationWriter` (`pipeline.py`) para que la topología sea testeable.
- `recursion_limit_for(n) = 6 * n + 25`.
- Un fallo de modelo marca `fallback=True` para **ese** finding; el bucle sigue.

## ContextOptimizer (`optimizer.py`) — reglas duras

- **Payload cerrado** (`PAYLOAD_KEYS`, 8 claves): `finding_type`, `field_source`,
  `evidence_snippet`, `confidence`, `heuristic_severity`, `target_domain`,
  `asset_content_type`, `asset_url`. Nada más viaja al modelo.
- `finding_id` y `had_baseline_severity` son bookkeeping del pipeline: **nunca**
  dentro del payload.
- **Cero bytes**: `_ensure_json_safe` lanza si un valor es bytes o no serializa.
- **1 finding por llamada** (MVP): nunca se mezcla evidencia de findings distintos.
- Presupuesto **~1.500 tokens** (`MAX_CALL_TOKENS`), estimado `len(text)//4`
  (`estimate_tokens`, mínimo 1). Snippet sobredimensionado → truncado con `...`
  y el corte **se loguea**.
- Tope de coste: `max_findings` por run (`METATRACER_MAX_AGENT_FINDINGS`, default 50).
  El exceso se prioriza por tipo: **gps → internal_path → debug_comment → email →
  software_version**. Los descartados conservan su baseline heurístico intacto.

## Modelos (`llm.py`)

- Fuerte (`METATRACER_LLM_MODEL`) para análisis/severidad; rápido
  (`METATRACER_FAST_MODEL`) para títulos y resumen ejecutivo.
- Cliente `ChatOpenAI` contra `METATRACER_LLM_BASE_URL` (API compatible OpenAI).
- Reintentos (`RetryPolicy`): **3 intentos**, backoff exponencial con jitter
  (`wait_initial_s=1.0`, `wait_max_s=8.0`) sobre 429/5xx/timeouts/errores de
  conexión. `timeout=60.0`, `max_tokens=2000`.
- Clave vacía o fallo agotado → `AgentUnavailableError` → fallback heurístico.

## Structured output (`schemas.py`)

- `AgentFindingAnalysis`: severity, justification, impact_analysis, remediation,
  reproduction_steps (`list[str]`), cited_evidence.
- `FindingTitle`: title. `ReportSummary`: executive_summary.
- `AgentFindingEvaluation`: lo anterior + title, ya validado por el guard.
- Un reintento de schema y luego fallback. Enums cerrados de `db/models.py`.

## Guard post-LLM (`guard.py`) — la garantía real

El prompt **no** es la defensa; este validador determinista sí. Puede bajar,
reparar o rechazar — **nunca** subir ni reescribir evidencia:

1. `cited_evidence` debe ser **substring** del snippet (whitespace colapsado,
   casefold). Cita inventada → se sustituye por el snippet y baja un rank.
2. Techos por tipo (`HEURISTIC_CEILINGS`) **y** severidad que el snippet soporta
   (re-derivada con el heurístico). GPS a `critical` es imposible.
3. Baseline del operador (feedback) es cota superior.
4. Pasos de reproducción con vocabulario de payload (`msfvenom`, `mimikatz`,
   `nc -e`, `bash -i`, `/etc/passwd`, `| sh`, `ignore previous`, …) se eliminan;
   si no queda ninguno, se usa la plantilla defensiva heurística.
5. Prosa (`justification`/`impact`/`remediation`/`title`) con ese vocabulario se
   sustituye por la plantilla; >1.500 chars se trunca.
6. Incoherencia texto↔severidad (la prosa cita otro nivel) → **rechazo** y
   fallback.

Ver skill `risk-rubric` para los techos y el anclaje.

## Payload al modelo (`message_payload`)

La evidencia se delimita (`<<<EVIDENCE>>>…<<<END>>>`) y el contexto RAG viaja
como `historical_not_evidence`, **nunca** como evidencia. El payload persistido
en el finding no cambia.

## Resiliencia y coste

- Caché por run (`_analysis_cache`): el mismo payload cerrado sin `asset_url`
  reutiliza la respuesta del modelo fuerte (TASK-34).
- Feedback (`memory.py`) y RAG (`knowledge.py`) son **no-op** sin datos.
- `METATRACER_LLM_CONCURRENCY` limita llamadas en vuelo (default 1).

## AgentLog (higiene de secretos)

Sí: tokens, modelo, latencia y la evaluación estructurada.
**Nunca**: API key, cabeceras de auth, prompt completo.

## Checklist

- [ ] Nada nuevo dentro de `PAYLOAD_KEYS` sin actualizar el contrato.
- [ ] Cero bytes y cero HTML/JS fuente en el payload.
- [ ] Un finding por llamada; presupuesto aplicado y corte logueado.
- [ ] El guard solo baja/rechaza; `finding_type` y `evidence_snippet` inmutables.
- [ ] Todo fallo de modelo deja el finding con baseline heurístico (nunca se borra).
- [ ] Tests con LLM fake; cero APIs reales en CI.
