# Producto ahora — MetaTracer v3.2 (overlay v3.4; specs 46–48 closed)

Herramienta de descubrimiento de metadata sensible para bug bounty y red team **autorizados**.
Pipeline: ingest → detectores deterministas → clasificador heurístico → agente LangGraph
opcional (guard post-LLM) → reportes. Un solo orquestador; CLI y API/UI muestran los mismos findings.

## Superficie

- **Safety:** scope confirmado, wrapper HTTP único, cero binarios persistidos, redirects in-scope, loopback bloqueado.
- **Fuentes:** PDF, imagen JPEG/PNG/TIFF/WebP/GIF (EXIF/XMP/IPTC; comentario GIF), SVG metadata/RDF only (nunca el dibujo), HTML, cabeceras HTTP, comentarios JS, propiedades OOXML/ODF (nunca el cuerpo). CSS `url()` in-scope encola imágenes/PDF; el CSS no se persiste.
- **Hallazgos implementados:** `gps`, `email`, `internal_path`, `software_version`, `debug_comment`, `internal_endpoint`, `cloud_storage`.
- **Plataforma:** scopes persistentes, dashboard, notificaciones, webhooks HMAC, KB portable, watch `--once`/`--interval`/`--cron` UTC (delta = findings **nuevos**), PostgreSQL + pgvector con embeddings 384-d (MiniLM ONNX local si hay extra `[onnx]` y path; si no, hashing-trick), auth cookie + CSRF, roles operator/viewer, multi-usuario, retención, abort de runs, triage de findings (`triage_status`, masivo TASK-42), investigations (agrupa runs; CLI `metatracer investigation`) y correlación de valores. Exports: `export.redaction` solo en el fichero (`none`/`contacts`/`coordinates`/`all`); API y CLI default `none`; la UI propone `contacts`. Conectores (RDAP, Wayback, Common Crawl): lista cerrada, apagados por defecto, `connector.status`; no amplían el scope. Lock de scan durable entre procesos; `resume` de un `aborted`; `GET /api/metrics`; alias `/api/v1`.
- **UI:** Next.js en `web/` **en español**, un origen (Caddy: `/api` → FastAPI). Investigations: `/investigations` y ficha de grupo; correlaciones y sugerencias de triage en el run. Triage masivo y densidad en el panel de findings. Búsqueda global: `/search` y paleta (`GET /api/search`). Hallazgos en split pane ≥1024px (`[`/`]`); Comparar en nav; Integraciones en paleta. Cobertura: histograma MIME y tabla email/autor. Reportes exportados y CLI siguen en inglés.

## Lo que el código no hace (specs reserved 49–51)
- `finding_type: secret` — [49](49-secret-finding.md) (enum **al activar**).
- Deltas watch desaparecido / severity-up (`PAYLOAD_KEYS`) — [50](50-watch-deltas.md).
- Ingesta de carpeta local sin red — [51](51-local-ingest.md).
