---
name: detector-patterns
description: Patrones y trampas de los cinco detectores deterministas de MetaTracer (gps, email, internal_path, software_version, debug_comment), niveles de confidence y consolidación/dedup. Usar al escribir o ajustar cualquier fichero de src/metatracer/detectors/ (gps.py, email.py, paths.py, software.py, debug.py, patterns.py, consolidator.py, registry.py) o al investigar falsos positivos y negativos de detección.
---

# Detectores deterministas

Los detectores leen solo `RawMetadataItem` y emiten `FindingDraft` con
`detector_method="rule"` y **sin severity**. Referencia: `.aicontext/tasks/02-specific-detection.md`.

## Contrato (`detectors/base.py`)

- Entrada: `Sequence[RawMetadataItem]`. **Prohibido abrir el fichero original.**
- Salida: `FindingDraft(finding_type, field_source, evidence_snippet, confidence)`.
- Normalización previa a cualquier match: `normalize_text` (NFC + strip).
- Snippet: `snippet()` colapsa whitespace y corta a **150** chars con `...`
  (`MAX_SNIPPET_CHARS`); `snippet_around()` centra una ventana en el match.
  GPS es la excepción: una sola línea de coordenadas, sin truncar.
- Un detector que lanza no tumba el run: `DetectorRegistry.detect_all` lo
  captura, loguea el **tipo** de excepción y sigue con los demás.

## GPS (`gps.py`)

- EXIF llega crudo de TASK-01: DMS como array JSON de racionales `"num/den"`
  + ref `N/S/E/W`. Aquí se aplica `grados + min/60 + seg/3600`.
- XMP llega **ya decimal**: solo se valida rango, **nunca** se reaplica DMS.
- Rechazos: falta una coordenada, no finito, `lat` fuera de `[-90,90]`,
  `lon` fuera de `[-180,180]`, o null island.
- **Null island**: `abs(lat) < 1e-5 and abs(lon) < 1e-5` (~1 m) es un bloque
  GPS vacío, no un lugar. El mismo umbral vive en `classification/anchor.py`
  (`parse_gps_line`): si cambias uno, cambia el otro.
- Ref de hemisferio desconocida → se descarta (no se inventa el signo); ref
  ausente → positivo (default documentado).
- Snippet: `Latitude: 40.416775, Longitude: -3.703790`, y `, Altitude: N` si
  existe, **sin unidad** (el tag no la lleva; inventarla está prohibido).
- `confidence` siempre `high`; `field_source` es `EXIF:GPSInfo` o `XMP:GPS`.

## Email (`email.py`)

- Regex práctica (no RFC 5322): `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`.
- Falsos positivos vetados (TASK-34): `_RETINA_FILENAME_RE` (`@2x.`), TLDs de
  fichero (`png`, `jpg`, `js`, `css`, `pdf`, `woff2`, …) y TLDs reservados
  (`test`, `invalid`, `example`, `localhost`).
- `TOOL_DOMAIN_BLACKLIST`: dominios de herramienta/registro (`adobe.com`,
  `apple.com`, `microsoft.com`, `w3.org`, `example.com`, `test.com`,
  `github.com`, `gitlab.com`, `jsdelivr.com`, …). Comparación lowercase y
  cubre subdominios. `support@adobe.com` es ruido del productor, no del target.
- Snippet = el email exacto, nunca el párrafo.
- Confidence: `high` si el valor **es** el email (con corchetes/comillas
  alrededor permitidos); `medium` si está embebido en prosa.

## Internal path (`paths.py`)

- Detecta Windows drive, UNC y rutas Unix/macOS.
- **No** detecta: `/opt` y `/usr` genéricos, rutas relativas, `http://`,
  `xmlns:`. Ante la duda, no emitir (la rúbrica prefiere infra-detección).
- TASK-34 añadió `/private/tmp`, `Program Files`, `AppData` fuera de `Users`.
- La severidad se decide después (usuario/UNC ⇒ techo `high`), no aquí.

## Software version (`software.py`)

- Nombre **+** versión numérica obligatoria: `_VERSION_RE` (`\bv?\d+(?:\.\d+)+…`).
- `Microsoft Word` sin versión **no es finding** (queda como metadata cruda).
- `_VERSION_ONLY_KEYS` (`x-aspnet-version`, `x-aspnetmvc-version`, `x-version`):
  el nombre del header identifica el stack, así que **el número basta**.
- `_PERSON_KEYS` (`dc:creator`) es una persona, no un producto: no emitir.
- Nada de findings `info` "por si acaso".

## Debug comment (`debug.py` + `patterns.py`)

- Patrones **compartidos** con el clasificador en `detectors/patterns.py`
  (una sola copia para que no deriven, TASK-33). No los dupliques.
- Fuertes: `TODO|FIXME|DEBUG|XXX|HACK` seguidos de `:`, `NOT FOR PUBLIC RELEASE`,
  tickets `JIRA-\d+`, `GL-\d+`, `#ISSUE-\d+`.
- Débiles: `CONFIDENTIAL|INTERNAL|DRAFT|TEST`, solo si el valor es corto
  (`_WEAK_MAX_CHARS = 100`).
- **Un finding por campo, no por keyword.** Las claves `comment`/`description`
  cubren `html:comment` y `js:comment` sin detector nuevo.

## Consolidación (`consolidator.py`)

- Firma: `sha256(f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}")`
  (`dedup_signature`). Unique constraint `(asset_id, dedup_signature)` en BD.
- Drafts con la misma firma se fusionan: `field_source` = origenes únicos
  ordenados unidos con `" | "`; si disienten en confidence, **gana la más alta**.
- `finding_identity(asset_url, type, snippet)` es la variante **entre runs**
  (TASK-35, para compare/watch): no usa `asset_id`, que cambia en cada run.

## Checklist

- [ ] Cambio de regex: cuantificadores acotados, sin anidar, sobre valor ya truncado (ReDoS, amenaza 6).
- [ ] Ningún detector asigna `severity`.
- [ ] Snippet ≤ ~150 chars y sin saltos de línea (GPS: una línea).
- [ ] Un cambio en `patterns.py` mantiene coherentes detector y clasificador.
- [ ] Test negativo por detector para el falso positivo que motivó el cambio.
- [ ] Null-island y umbrales GPS coherentes con `classification/anchor.py`.
