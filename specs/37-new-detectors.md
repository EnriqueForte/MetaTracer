# Spec 37 — Detectores y namespaces reservados

**Estado:** closed (2026-11-05)  
**Agente previsto:** `pipeline-engineer`  
**Skill:** `detector-patterns`, `metadata-extraction`, `risk-rubric`  
**Task:** [TASK-37](../.aicontext/tasks/37-new-detectors.md)

## Intención

Implementar lo que los contratos **ya nombran** y el código **no debía emitir** hasta esta slice:

- `finding_type`: `internal_endpoint` (IPv4 RFC1918 o hostname `.internal`/`.corp`/`.local`/`.lan`/`*.svc.cluster.local`, techo `medium`)
- `finding_type`: `cloud_storage` (host S3/GCS/Azure Blob/R2, techo `high`; el producto **no pide** esa URL)
- `namespace`: `ooxml` \| `odf` — propiedades del paquete, **nunca** el cuerpo del documento

Safety: magic-bytes / allowlist; cero body persistido; detectores sin `severity`.

El código (`detectors/network.py`, `extractors/office.py`, rúbrica) ya estaba en el árbol; TASK-37 lo desbloquea en SDD y cierra tests de borde.

## Fuera de alcance

Abrir el documento Office como texto. Descargar el bucket. Nuevos `finding_type` no registrados.

## Dependencias

Contratos en `tasks/README.md`. Rúbrica: techos citados allí; `risk-rubric` en la misma slice.
