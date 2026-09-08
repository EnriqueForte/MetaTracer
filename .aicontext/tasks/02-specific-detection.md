# TASK-02: Detección Específica (Detectores Deterministas)

**Módulo:** Detección de Hallazgos  
**Referencia PRD:** [Detección Específica](../features/02-specific-detection.md)  
**Dependencias:** [TASK-00](00-architecture-and-safety.md), [TASK-01](01-metadata-extraction.md)  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Motor determinista que lee `RawMetadataItem` y emite `Finding` de los 5 tipos del MVP. Preferir regex/parsers reproducibles. Los agentes **no** sustituyen esta etapa.

Los detectores rellenan tipo, evidencia, confianza y método. **`severity` se deja `NULL`.** Clasificar es TASK-03/TASK-05.

---

## 2. Subtareas Detalladas

### Subtarea 2.0: Contrato del detector

```python
class Detector(Protocol):
    finding_type: FindingType
    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]: ...
```

`FindingDraft` incluye `finding_type`, `field_source`, `evidence_snippet`, `confidence`, `detector_method="rule"`. Un `DetectorRegistry` ejecuta los 5 detectores sobre los items de un asset y pasa los drafts al consolidator.

Entrada: **solo** metadata estructurada. Prohibido abrir el archivo original.

Normalizar texto (strip, NFC) antes de matchear. Snippet máximo ~150 caracteres salvo GPS (una línea de coordenadas).

---

### Subtarea 2.1: `GpsDetector`

- **2.1.1. DMS → decimal WGS84:**  
  `decimal = degrees + minutes/60 + seconds/3600`. Hemisferios `S` y `W` → signo negativo.  
  Si el valor **ya** viene decimal (XMP), no reaplicar la fórmula; validar rango.
- **2.1.2. Filtros:** lat ∈ [-90, 90], lon ∈ [-180, 180]. Descartar `(0, 0)` y valores no finitos.
- **2.1.3. Finding:**
  - `finding_type = gps`
  - `field_source = EXIF:GPSInfo` o `XMP:GPS`
  - `evidence_snippet` ejemplo: `Latitude: 40.416775, Longitude: -3.703790`
  - `confidence = high`
  - Altitud: incluirla en el snippet si existe; no inventar unidades si no vienen en la tag.

---

### Subtarea 2.2: `EmailDetector`

- **2.2.1. Regex práctica (no RFC 5322 completa):**  
  `r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'`  
  Campos: Author, Creator, Producer, Description, Comments, Copyright, Artist, `dc:creator`, y el resto de values del asset (barato y evita falsos negativos).
- **2.2.2. Blacklist de dominios de herramienta:**  
  `adobe.com`, `apple.com`, `microsoft.com`, `w3.org`, `xml.org`, `example.com`, `localhost`, `example.org`. Comparar el dominio del email en lowercase.
- **2.2.3. Finding:**
  - `finding_type = email`
  - `evidence_snippet` = el email exacto (no el campo entero si es un párrafo)
  - `confidence = high` si el value del campo es esencialmente el email; `medium` si está embebido en prosa larga

---

### Subtarea 2.3: `InternalPathDetector`

- **2.3.1. Windows drive:**  
  `r'[A-Za-z]:[\\/](?:Users|Documents and Settings|Users\\|Windows|inetpub|xampp)[\\/][^\s"<>|]+'`  
  Cubrir **también** `C:/Users/...` (slash Unix).
- **2.3.2. UNC:** `r'\\\\[A-Za-z0-9_.\-]+\\[A-Za-z0-9_$.\-]+(?:\\[^\s"<>|]+)*'`
- **2.3.3. Unix/macOS:** `r'(?:/home|/Users|/private/var|/var/www|/srv|/root)/[^\s"<>|]+'`  
  `/opt` y `/usr` solos son demasiado ruidosos: **no** matchear `/opt/` ni `/usr/` genéricos salvo que aparezca un home de usuario (`/opt/home/...` no hace falta). Si hay duda, no emitir finding (la rúbrica prefiere infra-detección a ruido).
- **2.3.4. Negativos:** `http://`, `https://`, `xmlns:`, `file:///` público, rutas relativas `./images/`.
- **2.3.5. Finding:** `internal_path`, `confidence = high` para `Users\`, UNC y `/home|/Users|/root`. `medium` para `/var/www` sin nombre de usuario (cualquier `/var/www/<segmento>`: un directorio de deploy no es un home de usuario; corregido en la auditoría post-MVP).

---

### Subtarea 2.4: `SoftwareVersionDetector`

- **2.4.1. Campos:** Producer, Creator, CreatorTool, Software, Application, y equivalentes XMP.
- **2.4.2. Patrón:** nombre + versión numérica (`Apache FOP Version 2.6`, `wkhtmltopdf 0.12.5`, `Adobe InDesign 18.2`, `macOS Version 14.5 (Build 23F79)`).
- **2.4.3. Sin número de versión o build → no hay finding.** `Microsoft Word`, `PDF`, `Quartz PDFContext`, `Canva` se quedan en metadata cruda. No crear findings `info` “por si acaso”.
- **2.4.4. Finding:** `software_version`, `confidence = high` si hay `x.y` o build; snippet = cadena de software+versión recortada.

---

### Subtarea 2.5: `DebugCommentDetector`

- **2.5.1. Campos de texto libre:** Comment, UserComment, Description, Subject, Keywords, `xmp:Note`, ImageDescription.
- **2.5.2. Keywords fuertes (confidence high):** `TODO:`, `FIXME:`, `DEBUG:`, `XXX:`, `HACK:`, `NOT FOR PUBLIC RELEASE`, tickets `JIRA-\d+`, `GL-\d+`, `#ISSUE-\d+`.
- **2.5.3. Keywords débiles (confidence medium):** `CONFIDENTIAL`, `INTERNAL`, `DRAFT`, `TEST` sin contexto de desarrollo. El clasificador podrá bajarlas a `low`/`info`.
- **2.5.4. Snippet:** hasta 150 caracteres alrededor del match, colapsando whitespace.
- **2.5.5. Finding:** `debug_comment`. Si el mismo campo matchea varias keywords, un finding por campo (no uno por keyword) salvo evidencias claramente distintas.

---

### Subtarea 2.6: `FindingConsolidator`

- **2.6.1. Firma:** `sha256(f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}")` → `dedup_signature`.
- **2.6.2. Dedup:** mismo asset + misma firma → un finding; `field_source` concatenado con ` | ` (ordenado, único).
- **2.6.3. Persistencia:** insertar ignorando conflictos del unique constraint. `severity` permanece `NULL`. `detector_method = rule`.
- **2.6.4. Actualizar `Run.total_findings`.**

---

## 3. Fuera de alcance de esta tarea

- Secretos/credenciales como tipo propio (si aparecen, caen en `debug_comment` u otro de los cinco).
- Clasificación de severidad y llamadas al LLM.
- Detección sobre HTML/JS/headers — cubierto por [TASK-09](09-source-expansion.md) (mismos cinco tipos; v1.2, completada).

---

## 4. Tests mínimos

`tests/unit/test_detectors.py` — un caso positivo por tipo + un documento limpio (cero findings) + dedup de email duplicado en Author y Creator + producer sin versión (cero findings de `software_version`) + `(0,0)` GPS ignorado.

---

## 5. Criterios de Aceptación (DoD)

- [x] PDF con `C:\Users\admin\Documents\file.pdf` → finding `internal_path` con evidencia exacta.
- [x] JPEG con EXIF GPS válido → `gps` con decimales correctos.
- [x] `jane.doe@target.corp` → `email`. `support@adobe.com` → no finding.
- [x] `Producer: Apache FOP 2.4` → `software_version`. `Producer: Microsoft Word` → no finding.
- [x] `TODO: remove staging credentials` → `debug_comment`.
- [x] Dos campos idénticos en el mismo asset → un finding.
- [x] Documento limpio → cero findings; el asset sigue `ok`.
- [x] Todos los findings insertados tienen `severity IS NULL`.
