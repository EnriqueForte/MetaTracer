# TASK-37: Detectores `internal_endpoint` / `cloud_storage` y namespaces OOXML/ODF

**Módulo:** `detectors/network.py`, `extractors/office.py`, rúbrica  
**Spec:** [specs/37-new-detectors.md](../../specs/37-new-detectors.md)  
**Dependencias:** v3.2, contratos en este README  
**Agente:** `pipeline-engineer`  
**Estado:** **Cerrada 2026-11-05.** Código y tests ya estaban en el árbol; esta slice activa el contrato SDD, desbloquea los enums reserved y cubre bordes RFC1918/GCS.

## 1. Objetivo técnico

Emitir los `finding_type` que los contratos ya nombraban:

- `internal_endpoint` — IPv4 RFC1918 (`10/8`, `172.16/12`, `192.168/16`) o hostname `.internal` / `.corp` / `.local` / `.lan` / `*.svc.cluster.local`. Techo heurístico `medium`. Loopback, `localhost` y públicas no salen.
- `cloud_storage` — host S3 (incl. regional), GCS, Azure Blob, R2. Se descarta query/fragmento (firmas). **No se pide la URL.** Techo `high`.

Y extraer namespaces `ooxml` / `odf`: solo propiedades del ZIP (`docProps/*.xml`, `meta.xml`). Nunca el cuerpo, thumbnails ni embeddings. Magic bytes ZIP + extensión/Content-Type de oficina; un ZIP genérico no se parsea.

Detectores **sin** `severity`. Un paquete hostil (`NotOfficePackage` / bombas ZIP / DOCTYPE) marca el asset `skipped`/`failed` y el run sigue.

## 2. Subtareas

### 37.1 Contrato SDD

- Spec 37 `reserved` → `active` → `closed`.
- `finding_type` `internal_endpoint` / `cloud_storage` y namespaces `ooxml` / `odf` dejan de ser reserved-implementable.
- Skills `detector-patterns`, `metadata-extraction`, `risk-rubric` (ya describían el comportamiento).

### 37.2 Código (ya en el árbol)

- `InternalEndpointDetector` + `CloudStorageDetector` en `detectors/network.py`, registrados en `DetectorRegistry`.
- `OfficeMetadataExtractor` en `extractors/office.py`, `AssetKind.office` en `sniff.py`, dispatch en `ingest.py`.
- `HEURISTIC_CEILINGS`, `RUBRIC_PROMPT_TEXT`, plantillas y `correlation.kind` `internal_endpoint`.
- `cloud_storage` es finding, no `correlation.kind`.

### 37.3 Tests

- RFC1918 (incl. `172.16/12`), sufijos internos, negativos (públicas, loopback, `172.15`/`172.32`).
- Cloud: S3 sin query, Azure, GCS, R2; `nots3.amazonaws.com` no match.
- Techos medium/high; prosa de storage dice que no se pidió la URL.
- OOXML/ODF: propiedades sí, cuerpo no; ZIP ajeno, ratio, cifrado, DOCTYPE, `.docx` HTML.

## 3. Fuera de alcance

Abrir el documento como texto. Descargar el bucket. Nuevos `finding_type`. Conectores (38). Redacción de export (39).

## 4. DoD

- [x] Detectores emiten los dos tipos sin `severity`
- [x] Extractor de oficina no lee el cuerpo
- [x] Tests de la slice verdes; ruff limpio
- [x] Spec 37 closed; MEMORY y backlog actualizados
