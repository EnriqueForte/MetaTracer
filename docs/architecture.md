# Arquitectura

[Volver al README](../README.md)

MetaTracer utiliza un único orquestador para la interfaz web, la API y la CLI. La interfaz web está en `web/` y la API está construida con FastAPI.

## Cómo trabaja el pipeline

1. **Safety** — scope confirmado, un único wrapper HTTP, redirects revalidados,
   proxies de entorno ignorados (`trust_env=False`).
2. **Ingesta** — crawl de profundidad 1, allowlist por magic bytes.
3. **Detectores** — reglas; la severidad queda vacía.
4. **Clasificador heurístico** — rúbrica con techos por tipo (siempre disponible).
5. **Agente** (opcional) — un hallazgo por llamada; si el modelo falla, queda
   la heurística.
6. **Informe y triaje** — el operador marca falsos positivos; no se reescribe
   la evidencia.

El LLM es opcional (`METATRACER_LLM_*` en `.env`). Sin clave, solo corre la
heurística.

## Qué detecta

| Tipo | Ejemplos |
| --- | --- |
| `gps` | Coordenadas EXIF / IPTC |
| `email` | Correos en metadata y comentarios |
| `internal_path` | Rutas de disco o UNC |
| `software_version` | Producto y versión en PDF / cabeceras |
| `debug_comment` | Comentarios HTML/JS de desarrollo |
| `internal_endpoint` | Hosts `.internal` / RFC1918 en metadata |
| `cloud_storage` | Hosts S3, GCS, Azure Blob, R2 |
| `secret` | Allowlist: `AKIA`, `ghp_`, PEM, JWT compacto **ya extraídos** |

Fuentes: JPEG/PNG/TIFF/WebP/GIF, SVG (solo RDF/metadata, nunca el dibujo),
PDF, HTML, cabeceras HTTP, comentarios JS, propiedades OOXML/ODF (nunca el
cuerpo). También una **carpeta local** (`--local` / `local_paths`): mismos
extractores, cero red. No se descomprimen ZIP genéricos ni se piden HEIC/AVIF.

Consulta el [estado actual del producto](../specs/current.md) y la [memoria del proyecto](../MEMORY.md) para conocer los contratos y la documentación de desarrollo vigente.
