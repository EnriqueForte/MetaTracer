# TASK-51: Ingesta local de carpeta

**Módulo:** `extractors/local.py`, `extractors/ingest.py`, `ScanRequest`, CLI `scan --local`, wizard  
**Spec:** [specs/51-local-ingest.md](../../specs/51-local-ingest.md)  
**Dependencias:** TASK-01, TASK-09, TASK-37, TASK-48  
**Agentes:** `pipeline-engineer`, `ui-engineer`, `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-13.**

## 1. Objetivo técnico

Alimentar los **mismos** sniff + extractores desde un directorio o lista de
ficheros en disco. Cero `safe_httpx_request`. Scope confirmado solo para
etiquetar findings/reportes (dominio del engagement). Un asset ilegible no
tumba el run. Cero bytes en SQLite/Postgres, logs o LLM.

## 2. Subtareas

- `ScanRequest.local_paths`: no mezclar con `targets` HTTP. `targets` vacío
  permitido solo si hay `local_paths`.
- Walker: extensiones allowlist (`FILE_EXTENSIONS` + `.html`/`.htm`); no seguir
  symlinks; no unpack `.zip`/`.rar`/`.7z`; magic bytes como ingest remota.
- `Asset.source_url` / `final_url`: `file:` URI. `ingestion_stats.source=local`.
- CLI `--local` (repetible). API el mismo body. UI: rutas **en el servidor**.
- HTML local: extraer metadata; **no** seguir enlaces (cero red).

## 3. Fuera de alcance

Ejecutar binarios. Preview. Unpack de archivos. Sembrar crawl Wayback. Dorks.
File shares autenticados. `METATRACER_ALLOW_LOOPBACK` en distro.

## 4. DoD

- [x] Ninguna llamada HTTP en el camino local
- [x] Generic zip → `unsupported_type`; Office ZIP → propiedades-only
- [x] Asset fallido → `failed`/`skipped` y el run sigue
- [x] Spec 51 closed
