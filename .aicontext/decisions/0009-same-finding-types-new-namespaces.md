# ADR-0009: Mismos cinco `finding_type`, namespaces nuevos

**Fecha:** 2026-09-06  
**Estado:** Aceptada (v1.2 / [TASK-09](../tasks/09-source-expansion.md))  
**Slice:** Expansión de fuentes

## Contexto

Tras validar el MVP, el leak más visible que *no* encajaba en un tipo era un nombre de autor
en un PDF público. En paralelo, el crawl de profundidad 1 ya descargaba HTML y cabeceras
HTTP y los tiraba: solo servían de semilla para descubrir PDFs e imágenes.

Había dos formas de crecer: añadir tipos (`author_name`, secretos, CSP…) o tratar HTML /
headers / comentarios JS como **más `RawMetadataItem`** para los cinco detectores existentes.

## Decisión

Ampliar `RawMetadataItem.namespace` a `http` | `html` | `js` y dejar `finding_type` en los
cinco valores del MVP: `gps`, `email`, `internal_path`, `software_version`, `debug_comment`.

`author_name` queda **fuera**. Un autor con email ya dispara `email`. Un nombre sin email no
es un finding tipado hasta que se actualice primero el contrato de enums.

Los detectores no se reescriben: recorren todos los values. `SoftwareVersionDetector` gana
claves de recon; `DebugCommentDetector` ya cubre `comment` / `description`.

## Alternativas descartadas

- **Nuevo `finding_type` por fuente.** `html_comment` vs `debug_comment` duplicaría la rúbrica,
  las plantillas, el guard y la UI. La fuente ya está en `field_source` (`html:comment`).
- **Añadir `author_name` en la misma slice.** Exige contrato, rúbrica, techo heurístico y
  tests de ruido (cualquier PDF de Office trae un Author). No era el cuello de botella de
  v1.2: el crawl ya veía HTML y lo ignoraba.

## Consecuencias

- Un `Server: nginx/1.18.0` y un `<!-- TODO: ... -->` salen como `software_version` y
  `debug_comment`, no como tipos nuevos.
- El clasificador y el agente no cambian de contrato; el `{tool}` de repro pasa a `curl`
  cuando `field_source` empieza por `http:` / `html:` / `js:`.
- Añadir `author_name` más adelante sigue siendo un cambio de contrato, no un hotfix.
