---
name: metatracer-onnx
description: Embeddings locales ONNX de MetaTracer (all-MiniLM-L6-v2, 384-d) detrás de KnowledgeRetriever. Usar al tocar agents/embeddings.py, knowledge_pg._embed, extra [onnx] o METATRACER_ONNX_*.
---

# Embeddings ONNX (TASK-40)

Sustituye solo `_embed`. Dimensión **384**. Misma interfaz `KnowledgeRetriever`.

## Carga

1. `METATRACER_ONNX_MODEL_PATH` apunta a un `.onnx` **local**.
2. Extra `[onnx]` instalado (`onnxruntime`, `tokenizers`).
3. Tokenizer: `METATRACER_ONNX_TOKENIZER_PATH` o `tokenizer.json` junto al modelo.

Si falta cualquiera: **hashing-trick**. Un fallo de ONNX no tumba el run.

## Prohibido

- Descargar pesos o vocabulario en runtime.
- `huggingface_hub`, APIs de embeddings, HTTP.
- Cambiar la dimensión de `knowledge_vectors`.
- Meter ONNX en `requirements.in` / imagen default.

Tras cambiar de hashing a ONNX hay que **rebuild** del índice derivado (espacios distintos).
