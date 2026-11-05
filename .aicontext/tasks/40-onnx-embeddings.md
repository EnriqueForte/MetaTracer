# TASK-40: Embeddings ONNX locales (Eje B leftover)

**Módulo:** `agents/embeddings.py`, `agents/knowledge_pg.py`  
**Spec:** [specs/40-onnx-embeddings.md](../../specs/40-onnx-embeddings.md)  
**Dependencias:** TASK-23  
**Agentes:** `llm-agent-engineer`, `safety-guardian` (deps)  
**Estado:** **Cerrada 2026-11-05.** Extra opcional `[onnx]`; Docker e instalación default siguen en hashing-trick.

## 1. Objetivo técnico

Sustituir `_embed` (384-d) por MiniLM ONNX **cuando** el operador apunta a un `.onnx` local
y tiene el extra instalado. Misma interfaz `KnowledgeRetriever`. Sin red. Si ONNX no carga,
hashing-trick (regla 5: no tumbar el run).

## 2. Subtareas

- Extra `onnx`: `onnxruntime>=1.17.0,<2` y `tokenizers>=0.20.0,<1`. No van en `requirements.in`
  (imagen default sin nativos ONNX). Lista TASK-00 actualizada en el mismo cambio.
- Settings `METATRACER_ONNX_MODEL_PATH` y `METATRACER_ONNX_TOKENIZER_PATH` (vacío = fallback).
- Tokenizer: `tokenizer.json` junto al modelo si el path de tokenizer está vacío.
- Mean-pool + L2; geometría 384. Rebuild del índice derivado al cambiar de backend.
- Cero `huggingface_hub`, cero HTTP.

## 3. Fuera de alcance

GPU. Cambiar dimensión. API de embeddings. Descargar pesos. Vendorizar el `.onnx` en git.

## 4. DoD

- [x] Path vacío o extra ausente → hashing-trick, tests de TASK-23 verdes
- [x] Sesión ONNX mockeada produce 384-d L2
- [x] Sin red en el módulo de embeddings
- [x] Spec 40 closed; MEMORY y backlog actualizados
