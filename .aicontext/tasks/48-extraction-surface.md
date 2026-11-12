# TASK-48: Superficie de extracción (propiedades-only)

**Módulo:** `extractors/sniff.py`, `image.py`, `svg.py`, `crawler.py`, `targets.py`, `ingest.py`; `detectors/gps.py`, `network.py`  
**Spec:** [specs/48-extraction-surface.md](../../specs/48-extraction-surface.md)  
**Dependencias:** TASK-01, TASK-09, TASK-37  
**Agentes:** `pipeline-engineer`  
**Estado:** **Cerrada 2026-11-12.**

## 1. Objetivo técnico

Ampliar allowlist y campos que alimentan detectores existentes: GIF, SVG metadata-only, GPS IPTC/XMP, URIs `s3://`/`gs://`/Spaces/Wasabi, `url()` CSS in-scope. Cero bytes persistidos. Sin `finding_type` nuevo.

## 2. Subtareas

- Magic GIF87a/GIF89a; `.gif` en `DOCUMENT_EXTENSIONS`; comment + XMP en extractor de imagen.
- SVG: clasificar si el lookahead contiene `<svg`; extraer solo `<metadata>` / RDF / Dublin Core (`xmp`). Sin `<svg>` → `unsupported_type`. No persistir el dibujo.
- `GpsDetector`: coordenadas en namespace `iptc` (decimal o DMS), además de EXIF/XMP.
- `CloudStorageDetector`: `s3://`, `gs://`, `*.digitaloceanspaces.com`, `*.wasabisys.com`. Sin GET. Strip query.
- Crawler: quitar `.gif`/`.svg` de never-document; `url()` de stylesheets in-scope (GET CSS, no Asset). `srcset`/`picture`/`og:image` ya existían.
- HEIC/AVIF: OOS (hace falta paquete).

## 3. Fuera de alcance

Video, OLE, RTF, JSON APIs, sourcemaps, AST, cuerpo Office, spec 49 `secret`.

## 4. DoD

- [x] GIF con comment/XMP produce campos; raster no se guarda
- [x] SVG con RDF emite `xmp`; SVG sin `<svg` en lookahead se omite
- [x] GPS IPTC decimal produce finding; sin geocoding
- [x] `s3://` / Spaces en metadata → `cloud_storage`; no hay HTTP al bucket
- [x] CSS `url(photo.jpg)` in-scope se encola; no hay Asset `.css`
- [x] Spec 48 closed al terminar
