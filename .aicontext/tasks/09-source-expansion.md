# TASK-09: Expansión de fuentes (v1.2)

**Módulo:** Ingesta y extracción + detectores existentes  
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Extracción de metadata](../features/01-metadata-extraction.md), [Detección específica](../features/02-specific-detection.md)  
**Dependencias:** TASK-00 … TASK-08 (v1.0 cerrado, v1.1 usable)  
**Estado:** Completada  

---

## 1. Objetivo técnico

Tratar HTML, cabeceras HTTP y comentarios JavaScript como fuentes de metadata de primer nivel, sin reescribir la ingesta ni añadir `finding_type`. Los cinco detectores del MVP corren sobre los nuevos `RawMetadataItem`.

La página HTML que hoy solo se usa como semilla del crawl (profundidad 1) se persiste como `Asset`. Las cabeceras recon-relevantes de **cualquier** descarga exitosa (PDF, imagen, HTML, JS) se persisten en namespace `http`. Los comentarios de scripts inline y de `.js` in-scope se persisten en namespace `js`.

Cero dependencias runtime nuevas: BeautifulSoup y `re` ya están en la lista cerrada.

---

## 2. Subtareas

### 9.1 Contratos

Ampliar `RawMetadataItem.namespace` (sigue siendo string, no enum SQL):

`exif` | `xmp` | `pdfinfo` | `iptc` | `http` | `html` | `js`

Actualizar `.aicontext/tasks/README.md` y el skill de contratos **antes** de persistir valores nuevos. Los cinco `finding_type` no cambian. `author_name` sigue fuera (candidato posterior; un autor con email ya dispara `email`).

### 9.2 Cabeceras HTTP (`namespace=http`)

Tras una descarga `ok`, persistir solo la allowlist de recon (nombres en minúsculas, ya normalizados por el gateway):

`server`, `x-powered-by`, `x-aspnet-version`, `x-aspnetmvc-version`, `x-generator`, `x-runtime`, `x-version`, `x-application-version`, `via`, `x-debug`, `x-debug-token`, `x-sourcemap`, `sourcemap`, `x-backend-server`, `x-served-by`, `x-redirect-by`, `x-pingback`

Nunca persistir: `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `www-authenticate`, `proxy-authenticate`. Aunque aparezcan en la respuesta, se descartan antes de `sanitize_value`.

Un asset `skipped`/`failed` sigue sin `RawMetadataItem` (incluido headers).

### 9.3 HTML como asset (`namespace=html`)

- La página fetchada por `PublicDocCrawler` se persiste **con el body ya leído** (sin segundo GET).
- Extraer, sin guardar el HTML completo: `title`; `meta` `author` / `generator` / `description` / `keywords` / `application-name` / `creator`; comentarios `<!-- -->` (saltar vacíos y condicionales `<!--[if`; tope 32 comentarios/asset).
- Tope de página 5 MB (ya existe). Valor >2 KB → `[truncated]`.
- Una URL con extensión de documento (`.pdf`, imagen) cuyo body parezca HTML **sigue** `unsupported_type`: no reciclar error pages como assets HTML.

### 9.4 JavaScript (`namespace=js`)

- Descubrir `<script src>` in-scope que termine en `.js` (misma profundidad 1, mismo cap `MAX_ASSETS_PER_RUN`).
- Extraer comentarios `//` y `/* */` de scripts inline (en el HTML) y del body de cada `.js`. Parser que salta strings; no un regex ingenuo sobre `https://`. Tope 32 comentarios/asset.
- No persistir el fuente completo. Un `.js` fallido no tumba el run.
- `TargetResolver`: una URL que acaba en `.js` es `TargetKind.file`.

### 9.5 Detectores y repro

Sin detectores nuevos. Ajustes mínimos:

- `SoftwareVersionDetector`: además de Producer/Creator/…, escanear `server`, `x-powered-by`, `x-generator`, `generator`, `x-runtime`, `x-aspnet-version`, `x-aspnetmvc-version`, `x-version`, `x-application-version`. En cabeceras que solo llevan el número (`x-aspnet-version: 4.0.30319`) no exigir nombre delante de la versión.
- `DebugCommentDetector`: las claves `comment` / `description` ya cubren `html:comment` y `js:comment`.
- `EmailDetector` / `InternalPathDetector`: ya recorren todos los values.
- Plantillas: si `field_source` empieza por `http:` / `html:` / `js:` (o el content-type es HTML/JS), el `{tool}` de reproducción es `curl`, no `exiftool`.

### 9.6 Safety (invariantes)

- Todo HTTP sigue por `safe_httpx_request`. Cero `httpx` crudo.
- Cero bytes de HTML/JS/archivo en SQLite. Cero body al LLM.
- Allowlist de headers: sin cookies ni Authorization.
- El HTML de la página cuenta contra `MAX_ASSETS_PER_RUN`.
- Loopback/privadas igual que en v1.0. Sin `--insecure`.

---

## 3. Fuera de alcance

- Nuevo `finding_type` (`author_name`, secretos, CSP, CORS).
- Crawl recursivo, autenticación, sourcemaps como asset, CSS, JSON APIs.
- Persistencia de *todas* las cabeceras de respuesta.
- Dependencias nuevas (lxml, js2py, etc.).
- Dashboard v2.0.

---

## 4. Tests mínimos

- `tests/unit/test_html_extractor.py` — title/meta/comentarios; no persiste el body; salta `<!--[if`.
- `tests/unit/test_http_headers.py` — allowlist; `Set-Cookie` / `Authorization` omitidos.
- `tests/unit/test_js_extractor.py` — `//` y `/* */`; `https://` no es comentario.
- `tests/unit/test_crawler.py` — `<script src>` in-scope se descubre; off-scope no.
- `tests/unit/test_ingest.py` — página HTML persistida como asset; `.pdf` con body HTML sigue `unsupported_type`.
- `tests/unit/test_detectors.py` — `Server: nginx/1.18.0` → `software_version`; `html:comment` con `TODO:` → `debug_comment`.
- `tests/integration/test_e2e_pipeline.py` — página leaky del mock origin produce hallazgos de header/HTML/JS.

---

## 5. Criterios de aceptación (DoD)

- [x] Un dominio cuya home es HTML persiste esa página como asset `ok` y extrae title/meta/comentarios.
- [x] `Server: nginx/1.18.0` en una respuesta `ok` produce finding `software_version` con evidencia anclada a `http:server`.
- [x] Comentario HTML `<!-- TODO: ... -->` y comentario JS `// FIXME: ...` producen `debug_comment`.
- [x] `<script src>` in-scope se descarga; uno off-scope no abre socket.
- [x] URL `.pdf` que devuelve HTML → `unsupported_type`, cero metadata HTML.
- [x] Cero `Set-Cookie` / `Authorization` en `raw_metadata_item`.
- [x] Cero dependencias runtime nuevas.
- [x] Un `.js` 404 no aborta el run.
