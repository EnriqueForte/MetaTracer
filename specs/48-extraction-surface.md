# Spec 48 — Superficie de extracción (propiedades-only)

**Estado:** closed (2026-11-12)  
**Agente previsto:** `pipeline-engineer`  
**Skill al abrir:** `metadata-extraction`, `detector-patterns`, `metatracer-safety-rules`  
**Task:** [TASK-48](../.aicontext/tasks/48-extraction-surface.md)

## Intención

Ampliar **qué archivos y campos** alimentan los detectores ya existentes, sin leer
cuerpos y sin tipos de hallazgo nuevos. Huecos frente a ExifTool/FOCA: GIF/SVG,
GPS fuera del par EXIF, URIs de cloud en valores, CSS solo como pista de descubrimiento.

## Alcance

- **GIF:** XMP / comentarios de archivo; magic-bytes allowlist; mismos namespaces
  `xmp` / `exif` / `iptc` si aplican. No persistir el raster.
- **SVG:** solo RDF / XML de metadata (p. ej. Dublin Core embebido), **no** el markup
  de dibujo como body. Si el sniff no puede separar metadata de dibujo de forma
  segura, `skipped` / `unsupported_type`.
- **GPS:** el detector `gps` honra coordenadas ya extraídas en IPTC/XMP, no solo el
  par EXIF DMS. Sigue sin geocoding ni reverse lookup.
- **`cloud_storage`:** patrones adicionales **sobre valores ya extraídos**: `s3://`,
  `gs://`, hosts Spaces/Wasabi. El producto **no** hace GET al bucket (spec 37).
- **Crawl:** `url()` en CSS **in-scope** solo para encolar imágenes/PDF ya allowlist.
  El `.css` no se persiste como body. Verificar `srcset` / `<picture>` / `og:image`
  en el crawler actual; no reimplementar si ya están.

HEIC/AVIF: **solo** si Pillow/dependencias actuales bastan. Si hace falta paquete
nuevo → OOS de esta slice (supply-chain aparte). Pillow actual no abre HEIC/AVIF
sin extra: quedan fuera.

## Fuera de alcance

Video/audio. OLE `.doc`/`.xls`/`.ppt`. RTF. JSON APIs. Sourcemaps como asset.
JS runtime / AST. Cuerpo Office. Descargar el bucket. `finding_type` nuevo (`secret`
es spec 49). Namespace SVG nuevo (se reutiliza `xmp` / `exif`).

## Dependencias

Spec 37 closed. Enums actuales en `.aicontext/tasks/README.md` (sin valores nuevos).
