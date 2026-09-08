# Característica: extracción de metadata

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** v1.0 + v1.2 cerradas  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Ingerir targets autorizados (URLs o dominios), descargar **assets públicos** y extraer metadata estructurada que las etapas posteriores puedan detectar, clasificar y reportar.

v1.0 cubre PDFs e imágenes. v1.2 añade páginas HTML, cabeceras HTTP de recon y comentarios JavaScript, **sin** nuevos `finding_type`. Detalle de implementación: [TASK-09](../tasks/09-source-expansion.md).

Esta característica cubre los pasos 1–3 del [flujo de usuario](user-flow.md): proporcionar targets, descargar documentos, extraer metadata.

## Valor para el usuario

Hunters y Red Teams dejan de recolectar archivos a mano. La herramienta convierte una lista de targets en un dataset de metadata consistente con URL de origen, tipo de asset y estado de extracción.

## En alcance (MVP)

- Entrada de targets: lista de URLs y/o dominios.
- Descubrimiento de PDFs, imágenes y scripts `.js` públicamente alcanzables desde esos targets (URLs directas y enlaces/`<script src>` in-scope en la página de entrada).
- Descarga solo de assets públicos. La página HTML del crawl (profundidad 1) se persiste como `Asset` con el body ya leído — sin segundo GET.
- Extracción de metadata de:
  - **PDFs** (info del documento / campos tipo XMP: autor, creator, producer, títulos, timestamps, software) — namespace `pdfinfo` / `xmp`.
  - **Imágenes** (campos tipo EXIF / IPTC / XMP: GPS, cámara/software, timestamps, autor).
  - **HTML** (title, meta allowlist, comentarios `<!-- -->`) — namespace `html`.
  - **Cabeceras HTTP** de recon en cualquier descarga `ok` — namespace `http`, allowlist cerrada.
  - **JavaScript** (comentarios `//` y `/* */` de scripts inline y de `.js` in-scope) — namespace `js`.
- Persistir cada asset y sus campos crudos en la base de datos local ([requisitos técnicos](07-technical-requirements.md)). Nunca el body HTML/JS ni bytes de archivo.
- Registrar fallos (inalcanzable, tipo no soportado, error de parseo) sin abortar todo el run.

## Requisitos

1. Aceptar uno o más targets como URLs o dominios desde [Web UI y CLI](06-interfaces.md).
2. Antes de cualquier descarga, aplicar [verificación de scope y modo seguro](08-ethics-legal-safety.md).
3. Descargar solo PDFs, imágenes, páginas HTML y `.js` in-scope públicamente accesibles en hosts autorizados.
4. Aplicar rate limiting conservador a todas las peticiones HTTP.
5. Extraer metadata en un registro estructurado por asset, incluyendo al menos:
   - URL de origen
   - URL final (tras redirects, si los hay)
   - content type / tipo de archivo
   - timestamp de recuperación
   - campos de metadata crudos clave/valor
   - estado de extracción (`ok`, `skipped`, `failed`) y motivo de error cuando no sea `ok`
6. No enviar bytes crudos del archivo al LLM. La [detección](02-specific-detection.md) y los [agentes](05-ai-agents.md) posteriores consumen campos estructurados y fragmentos cortos de evidencia.
7. v1.2 reutiliza la misma ingesta (`Asset` + `RawMetadataItem`) sin reescribir el pipeline: namespaces nuevos, mismos cinco `finding_type`.

## Criterios de aceptación

- Dada una URL de PDF in-scope, la herramienta la descarga y almacena la metadata de documento extraíble.
- Dada una URL de imagen in-scope con EXIF, almacena la metadata de imagen extraíble (incluido GPS cuando exista).
- Dado un dominio, descubre PDFs/imágenes/`.js` enlazados públicamente en hosts in-scope, persiste la home HTML como asset y los procesa.
- Dada una lista mixta con algunas URLs caídas o que no son documentos, el run continúa y reporta el estado por asset.
- Una URL con extensión de documento (`.pdf`, imagen) cuyo body sea HTML sigue `unsupported_type`: no se recicla una error page como asset HTML.
- Los hosts fuera de scope no se descargan cuando el modo seguro / checks de scope están activos.
- Los archivos crudos no se pasan al contexto de los agentes.

## Fuera de alcance

| Elemento | Cuándo |
| --- | --- |
| Nuevo `finding_type` (`author_name`, secretos, CSP, CORS) | Fuera de v1.2; un autor con email ya dispara `email` |
| Persistencia de *todas* las cabeceras o del body HTML/JS | Nunca |
| Sourcemaps como asset, CSS, JSON APIs | No en v1.2 |
| Documentos autenticados / tras paywall | Nunca en el MVP |
| Explotación activa o fuzzing de parsers | Nunca |
| Crawling recursivo a escala de Internet | Nunca |

## Dependencias

- **Upstream:** [Interfaces](06-interfaces.md), [Ética, legal y safety](08-ethics-legal-safety.md)
- **Downstream:** [Detección específica](02-specific-detection.md)

## Restricciones de safety

- Solo targets autorizados (scope de bug bounty, permiso explícito de auditoría o assets propios).
- Modo seguro activo por defecto: no hay escaneo hasta que el usuario confirme el scope.
- Rate limiting conservador; sin crawling agresivo.
- Permanecer en hosts in-scope; no seguir redirects que salgan del scope.
