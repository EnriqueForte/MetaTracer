# Producto ahora — MetaTracer v3.2

Herramienta de descubrimiento de metadata sensible para bug bounty y red team **autorizados**.
Pipeline: ingest → detectores deterministas → clasificador heurístico → agente LangGraph
opcional (guard post-LLM) → reportes. Un solo orquestador; CLI y API/UI muestran los mismos findings.

## Superficie

- **Safety:** scope confirmado, wrapper HTTP único, cero binarios persistidos, redirects in-scope, loopback bloqueado.
- **Fuentes:** PDF, imagen (EXIF/XMP/IPTC), HTML, cabeceras HTTP, comentarios JS, propiedades OOXML/ODF (nunca el cuerpo).
- **Hallazgos implementados:** `gps`, `email`, `internal_path`, `software_version`, `debug_comment`, `internal_endpoint`, `cloud_storage`.
- **Plataforma:** scopes persistentes, dashboard, notificaciones, webhooks HMAC, KB portable, watch `--once`/`--interval`/`--cron` UTC (delta = findings **nuevos**), PostgreSQL + pgvector con embeddings 384-d (MiniLM ONNX local si hay extra `[onnx]` y path; si no, hashing-trick), auth cookie + CSRF, roles operator/viewer, multi-usuario, retención, abort de runs, triage de findings (`triage_status`, masivo TASK-42), investigations (agrupa runs; CLI `metatracer investigation`) y correlación de valores. Exports: `export.redaction` solo en el fichero (`none`/`contacts`/`coordinates`/`all`); API y CLI default `none`; la UI propone `contacts`. Conectores (RDAP, Wayback CDX, Common Crawl): lista cerrada, apagados por defecto, `connector.status`; no amplían el scope. Lock de scan durable entre procesos; `resume` de un `aborted`; `GET /api/metrics`; alias `/api/v1`.
- **UI:** Next.js en `web/` **en español**, un origen (Caddy: `/api` → FastAPI). Investigations: `/investigations` y ficha de grupo; correlaciones y sugerencias de triage en el run. Triage masivo y densidad en el panel de findings. Reportes exportados y CLI siguen en inglés.

## Lo que el código no hace (aunque el enum exista)

Deltas watch “desaparecido / severity-up”. Ver leftover en `.aicontext/features/12-platform-v3.md`.
