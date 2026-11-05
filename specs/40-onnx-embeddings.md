# Spec 40 — Embeddings ONNX (Eje B leftover)

**Estado:** closed (2026-11-05)  
**Agente previsto:** `llm-agent-engineer`  
**Fuente:** `.aicontext/features/12-platform-v3.md` Eje B · TASK-23  
**Task:** [TASK-40](../.aicontext/tasks/40-onnx-embeddings.md)

## Intención

Sustituir el hashing-trick de `PgVectorKnowledgeIndex._embed` por `all-MiniLM-L6-v2` ONNX
(384-d **ya reservada**). Misma interfaz `KnowledgeRetriever`. Cero cambios de contrato en
`AgentPipeline` si se cumple eso.

Dependencia nueva = extra opcional `[onnx]` (`onnxruntime` + `tokenizers`), lista cerrada
TASK-00, sin red en runtime. Modelo local; no API de embeddings de terceros. Fallback:
hashing-trick si ONNX no carga (paquete ausente, path vacío, fichero ilegible).

## Fuera de alcance

Cambiar dimensión. Subir findings crudos a un proveedor. GPU como requisito. Descargar
pesos en runtime. Meter ONNX en la imagen Docker por defecto.

## Dependencias

TASK-23 cerrado. Skill: `metatracer-onnx` + `metatracer-supply-chain`.
