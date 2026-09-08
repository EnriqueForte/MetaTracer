# TASK-01: Ingesta, Descubrimiento y Extracción de Metadata

**Módulo:** Ingesta y Extracción  
**Referencia PRD:** [Extracción de Metadata](../features/01-metadata-extraction.md)  
**Dependencias:** [TASK-00](00-architecture-and-safety.md)  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Pipeline de ingesta de targets autorizados: descubrimiento superficial de PDFs e imágenes públicas, descarga asíncrona con rate-limit y extracción de metadata (EXIF, IPTC, XMP, InfoDict PDF) hacia `RawMetadataItem`.

Los bytes del archivo viven solo en un temporal durante la extracción y se borran después. No hay tabla de blobs.

---

## 2. Subtareas Detalladas

### Subtarea 1.1: Target Resolver y descubrimiento

- **1.1.1. `TargetResolver`:**
  - Entradas: URL de archivo (`https://target.com/doc.pdf`), página (`https://target.com/about`), dominio (`target.com`).
  - Validar cada host con `ScopeValidator` **antes** de clasificar.
  - Dominio sin esquema → tratar como `https://{domain}/` para el crawl de nivel 0.

- **1.1.2. `PublicDocCrawler`:**
  - Profundidad **1**: página de entrada + enlaces directos a documentos. Sin spidering recursivo.
  - Parsear HTML con BeautifulSoup: `<a href>` y `<img src>`.
  - Extensiones: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.webp`.
  - Resolver URLs relativas contra la URL final de la página.
  - Descartar de inmediato hosts fuera de scope (también `javascript:`, `data:`, `mailto:`).
  - Tope de página HTML: 5 MB. Si supera, `skipped` / no crawl.
  - Tope global: `MAX_ASSETS_PER_RUN` (default 50). Al alcanzarlo, dejar de encolar y registrar en el log del run.
  - User-Agent del cliente HTTP (ver 1.2). No ignorar robots.txt de forma agresiva; tampoco hace falta un crawler `robots` completo en el MVP (documentar: “crawl superficial de una página, no un bot a escala”).

---

### Subtarea 1.2: Cliente HTTP seguro

Todo tráfico pasa por el helper de TASK-00 (`safe_httpx_request`).

- **1.2.1. `httpx.AsyncClient`:**
  - `User-Agent: MetaTracer/1.0 (authorized security audit; +https://github.com/your-org/metatracer)` — sustituir la URL cuando exista el repo.
  - Timeouts: connect 10s, read 20s, pool 10s.
  - `follow_redirects=False`. Seguir a mano **máximo 5 hops**. En cada hop: `ScopeValidator` + `NetworkSafetyGuard`. Si el hop sale de scope → `RedirectOutOfScopeError`, asset `skipped` / `out_of_scope`, no leer el body.
- **1.2.2. `DomainRateLimiter`:** token bucket o sleep por dominio. Default `RATE_LIMIT_RPS=2` (~500 ms mínimo). Además, semáforo global de concurrencia (p. ej. 3 descargas simultáneas).
- **1.2.3. Tamaño y streaming:**
  - Intentar `HEAD` para `Content-Length` y `Content-Type`. Si HEAD no está permitido (405/501/red vacía), hacer `GET` con stream.
  - Si `Content-Length` > `MAX_FILE_BYTES` → `skipped` / `too_large`.
  - Stream a `NamedTemporaryFile(delete=True)` o borrado explícito en `finally`. Abortar si el acumulado supera el tope.
  - SHA-256 del stream. Si el hash ya existe en el mismo `run_id`, no re-extraer: asset `skipped` / `duplicate_hash` (se conserva la URL para trazabilidad).
- **1.2.4. Allowlist de tipo (no fiarse solo de la extensión):**
  - Tras descargar, comprobar magic bytes:
    - PDF: `%PDF`
    - JPEG: `FF D8 FF`
    - PNG: `89 50 4E 47`
    - TIFF: `II*\0` o `MM\0*`
    - WEBP: `RIFF....WEBP`
  - Content-Types aceptables: `application/pdf`, `image/jpeg`, `image/png`, `image/tiff`, `image/webp`, y `application/octet-stream` **solo** si el magic byte matchea.
  - Si no matchea → `skipped` / `unsupported_type`. HTML descargado por error no se “extrae” como PDF.

---

### Subtarea 1.3: `PdfMetadataExtractor`

- **1.3.1. InfoDict:** `/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator`, `/Producer`, `/CreationDate`, `/ModDate` → namespace `pdfinfo`. Fechas PDF `D:YYYYMMDDHHmmSS` → ISO 8601 UTC cuando sea parseable; si no, guardar el string crudo.
- **1.3.2. XMP:** `reader.xmp_metadata`. Namespaces `dc:`, `pdf:`, `photoshop:`, `xmp:`, `xmpMM:`. Capturar `CreatorTool`, `Producer`, `dc:creator`, `DocumentID`, `InstanceID`, y cualquier valor que parezca usuario/ruta (la detección tipada es TASK-02; aquí se persiste el campo).
- **1.3.3. Fallos:** `PdfReadError`, `is_encrypted`, truncados. Asset `failed` + `error_message`. El run continúa. No intentar romper cifrado.

---

### Subtarea 1.4: `ImageMetadataExtractor`

- **1.4.1. EXIF** con Pillow / piexif. Mapear tags con `TAGS` y `GPSTAGS`. Extraer Make, Model, LensModel, Software, Artist, Copyright, ImageDescription, DateTimeOriginal, DateTimeDigitized, DateTime.
- **1.4.2. GPS:** bloque `GPSInfo` intacto (DMS o decimal). Normalizar refs N/S/E/W. La conversión a decimal WGS84 es de `GpsDetector` (TASK-02), pero los valores crudos deben persistirse.
- **1.4.3. IPTC y XMP** en JPEG/PNG/WebP cuando existan (`XML:com.adobe.xmp`, chunks `tEXt`/`iTXt`). Si un formato no soporta un bloque, omitir sin fallar el asset.
- **1.4.4. Sanitización:** tuplas, `IFDRational`, bytes → string UTF-8 (replace) o JSON corto. **Nunca** guardar blobs (thumbnails EXIF, ICC). Si un valor supera ~2 KB, truncar con marca `[truncated]`.

---

### Subtarea 1.5: Persistencia y limpieza

- Crear `Asset` **antes** de extraer (status inicial implícito). Actualizar a `ok` / `failed` / `skipped`.
- Insertar `RawMetadataItem` en lote por asset.
- Borrar el temporal en `finally` aunque la extracción falle.
- 404/5xx → `failed` con el código HTTP. Body vacío → `skipped` / `empty_body`.
- Recalcular `Run.total_assets` al terminar la fase de ingesta.

---

## 3. Fuera de alcance de esta tarea

- HTML/headers/JS como fuente de findings — cubierto por [TASK-09](09-source-expansion.md) (v1.2, completada).
- Crawl recursivo, autenticación, paywalls.
- Detectores y LLM.
- Almacenar copias de los archivos en disco o en SQLite.

---

## 4. Tests mínimos

- `tests/unit/test_extractors.py` — usar archivos mínimos en `tests/fixtures/` (pueden ser generados a mano; el factory completo es TASK-07).
- `tests/unit/test_crawler.py` — HTML de fixture con enlaces in-scope, off-scope y relativa.
- `tests/unit/test_http_redirect_scope.py` — mock de redirect off-scope: no se lee el body.

---

## 5. Criterios de Aceptación (DoD)

- [x] PDF con Author/Creator/Producer persiste esos campos en `raw_metadata_item` ligados al asset.
- [x] JPEG con GPS persiste las etiquetas GPS crudas.
- [x] Dominio con HTML que enlaza PDFs in-scope: se descubren y se respeta el rate-limit.
- [x] 404, 500 o PDF dañado: asset `failed`/`skipped`, el run sigue.
- [x] Redirect fuera de scope: se cancela **antes** del body.
- [x] Magic bytes incorrectos → `unsupported_type`, no se parsea como PDF/imagen.
- [x] Los bytes del archivo no quedan en SQLite ni en `data/` tras terminar el asset.
- [x] Al superar `MAX_ASSETS_PER_RUN` no se siguen descargando archivos.
