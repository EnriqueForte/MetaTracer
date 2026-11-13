---
name: metadata-extraction
description: Pipeline de ingesta y extracción de MetaTracer (crawler, allowlist por magic bytes, extractores PDF/imagen/HTML/JS/cabeceras HTTP/Office, ingest local TASK-51, sanitización de valores y namespaces). Usar al tocar src/metatracer/extractors/ (ingest.py, local.py, crawler.py, sniff.py, targets.py, pdf.py, image.py, html.py, javascript.py, headers.py, office.py, xmp.py, sanitize.py, fields.py) o al diagnosticar por qué un asset se marca skipped/failed.
---

# Ingesta y extracción

De una URL in-scope a `Asset` + `RawMetadataItem`. **Nunca** se persisten bytes.
Referencia: `.aicontext/tasks/01-metadata-extraction.md`, `09-source-expansion.md`,
`51-local-ingest.md`.

## Ingesta local (`local.py`, TASK-51)

- `ScanRequest.local_paths` **o** `targets` HTTP, nunca ambos. Scope confirmado
  solo etiqueta el engagement; este camino **no** llama a `safe_httpx_request`.
- Walker: `FILE_EXTENSIONS` + `.html`/`.htm`. No sigue symlinks. No unpack de
  `.zip`/`.rar`/`.7z`. Magic bytes como ingest remota. HTML local no sigue enlaces.
- `Asset.url`: `file:` URI. `ingestion_stats.source=local`. Cero bytes persistidos.

## Resolución del target (`targets.py`)

- Entrada: fichero / página / dominio. Dominio sin esquema → `https://{dominio}/`.
- Validación de scope **antes** de cualquier petición.
- Una URL que acaba en `.js` es `TargetKind.file` (TASK-09).

## Allowlist por magic bytes (`sniff.py`) — amenaza 4

`SNIFF_HEADER_BYTES = 16`. Firmas exactas:

| Kind | Firma |
| :--- | :--- |
| PDF | `b"%PDF"` |
| JPEG | `b"\xff\xd8\xff"` |
| PNG | `b"\x89PNG\r\n\x1a\n"` |
| TIFF | `b"II*\x00"` (LE) o `b"MM\x00*"` (BE) |
| WEBP | `b"RIFF"` … `header[8:12] == b"WEBP"` |
| GIF | `GIF87a` / `GIF89a` |
| SVG | no es magic: lookahead 512 B con `<svg`; si no, `unsupported_type` |
| ZIP (oficina) | `b"PK\x03\x04"` / `PK\x05\x06` / `PK\x07\x08` **y** extensión/Content-Type de Office; un ZIP genérico no se parsea |

Reglas de `classify_downloaded_asset`:

1. **Los magic bytes mandan.** Si coinciden, deciden el tipo.
2. URL con **extensión de documento** que falla el magic → `unsupported_type`.
   Una página de error (`text/html`) **no** se recicla como asset HTML.
3. `.js` nunca se recicla como HTML; exige cuerpo textual
   (`b"\x00" not in header[:16]`).
4. HTML: content-type `text/html`/`application/xhtml+xml` o path `.html`/`.htm`.
5. JS: content-types `application/javascript`, `text/javascript`,
   `application/ecmascript`, `text/ecmascript`.

## Crawler (`crawler.py`)

Profundidad **1**. BeautifulSoup sobre `<a href>`, `<img src>`, `<script src>`
in-scope que acaba en `.js`. Descarta hosts off-scope y esquemas
`javascript:` / `data:` / `mailto:`. Topes: HTML **5 MB**,
`MAX_ASSETS_PER_RUN` (**50**) — la página HTML consume un slot. El body ya
crawleado se reutiliza: **sin segundo GET**.

## Extractores

- **PDF** (`pdf.py`): InfoDict → namespace `pdfinfo`; fechas `D:YYYYMMDDHHmmSS`
  → ISO 8601 cuando se pueden parsear; XMP (`dc:`, `pdf:`, `photoshop:`,
  `xmpMM:`). PDF cifrado o dañado → `failed` sin tumbar el run. El XMP se
  descomprime con **tope antes de inflar** (TASK-27, amenaza 5).
- **Imagen** (`image.py`): EXIF con Pillow (TAGS/GPSTAGS), bloque GPS **crudo**
  (la conversión DMS→decimal es del detector, no de aquí); IPTC/XMP en
  JPEG/PNG/WebP/GIF (comentario GIF → `exif:Comment`). Límite de píxeles de Pillow; tolerante a fallos.
- **SVG** (`svg.py`): solo `<metadata>` / RDF / Dublin Core (`xmp`). El dibujo no se persiste.
- **HTML** (`html.py`): `title`, meta **allowlist**, comentarios (se saltan los
  condicionales `<!--[if`). Namespace `html`.
- **Cabeceras HTTP** (`headers.py`): `HEADER_ALLOWLIST` de recon — `server`,
  `x-powered-by`, `x-aspnet-version`, `x-aspnetmvc-version`, `x-generator`,
  `x-runtime`, `x-version`, `x-application-version`, `via`, `x-debug`,
  `x-debug-token`, `x-sourcemap`, `sourcemap`, `x-backend-server`,
  `x-served-by`, `x-redirect-by`, `x-pingback`. `HEADER_DENYLIST` (defensa en
  profundidad, gana siempre): `authorization`, `proxy-authorization`, `cookie`,
  `set-cookie`, `www-authenticate`, `proxy-authenticate`.
- **JavaScript** (`javascript.py`): parser de `//` y `/* */` que **salta
  strings** (`https://` no es un comentario); recursión acotada (TASK-32).
- **XMP** (`xmp.py`): parser propio de `rdf:Description`, prefijos
  convencionales, contenedores `Seq/Bag/Alt` aplanados, `_MAX_DEPTH = 8`,
  `MAX_XMP_PACKET_BYTES = 5 MB`. XML roto → `{}`, nunca excepción.

## Namespaces (contrato cerrado)

`exif`, `xmp`, `pdfinfo`, `iptc`, `http`, `html`, `js`, `ooxml`, `odf`. Añadir uno exige
actualizar antes `.aicontext/tasks/README.md`. OOXML/ODF (`office.py`) leen solo
las propiedades del ZIP (`docProps/*.xml`, `meta.xml`), con tope de miembros,
tamaño declarado y ratio, y nunca el cuerpo del documento.

## Sanitización (`sanitize.py`)

- Tuplas, `IFDRational`, bytes → string UTF-8 o JSON corto. **Nunca blobs**
  (thumbnails, ICC, HTML/JS fuente).
- Valor > **2 KB** → truncado con `[truncated]`.
- `value` es **siempre texto** (contrato de `RawMetadataItem`).

## Ciclo de vida del asset

1. Crear `Asset` **antes** de extraer (estado `ok`/`skipped`/`failed`).
2. Temporal borrado en `finally` (PDF/imagen); HTML/JS se extraen en memoria.
3. SHA-256 para `duplicate_hash`; recalcular `Run.total_assets`.
4. `_EXTRACTION_INCOMPLETE = "extraction did not complete"` cuando el asset no
   terminó (abort/recovery).

## Checklist

- [ ] Ningún `httpx` crudo: todo por `safe_httpx_request` (rule 1).
- [ ] Magic bytes antes de Content-Type y extensión.
- [ ] Extension de documento + body HTML ⇒ `unsupported_type`, no HTML.
- [ ] Cero bytes persistidos ni enviados al LLM (rule 3).
- [ ] Cookies/Authorization nunca llegan a la BD (denylist).
- [ ] Tope aplicado **antes** de inflar (XMP/PDF) y al primer chunk (descarga).
- [ ] Asset fallido ⇒ `failed`/`skipped` + `error_message`; el run sigue (rule 5).
