# TASK-18: Exports bounty (v2.2)

**Módulo:** Integraciones — formatos de export orientados a bug bounty
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Generación de reportes](../features/04-report-generation.md), [Criterios de éxito](../features/09-success-criteria.md)
**Dependencias:** TASK-00 … TASK-17 (v1.0–v2.2 cerradas)
**Estado:** **Cerrada y validada 2026-09-13** — exportador CSV (`CsvReportExporter`) + plantilla bounty en texto plano (`BountyExporter`), `ExportFormat.csv\|bounty`, `--format all` escribe 5 ficheros, API `GET /api/runs/{id}/export?format=csv\|bounty` y botones en la Web UI. Verificado localmente: `ci-check.ps1` exit 0 (**453 passed** no-e2e + ruff limpio), suite e2e también en verde (**4 passed**), cobertura **89.30% ≥ 85%** (los dos módulos nuevos al 100%).

---

## 1. Objetivo técnico

TASK-04/TASK-08 ya exportan el write-up en **Markdown, JSON y HTML**. El
criterio de éxito del producto es *"reportes que enviarías de verdad"* a un
programa de bug bounty (HackerOne, Bugcrowd, Intigriti). Esos programas
aceptan, además de Markdown, dos formatos que hoy no genera MetaTracer:

1. **CSV** (`ExportFormat.csv`): una fila por finding con las **mismas
   columnas que el JSON** — pensado para triage, import en hojas de cálculo,
   correlación con el historial y re-uso por tooling externo.
2. **Plantilla bounty en texto plano** (`ExportFormat.bounty`): un write-up
   por finding listo para **copiar y pegar** en el formulario del programa
   (HackerOne / Bugcrowd / Intigriti comparten el patrón: Summary, Severity,
   Affected Asset, Steps to Reproduce, Impact, Remediation), con la misma
   ficha que el Markdown de TASK-04 pero **sin markdown** (los campos de
   texto de las plataformas no renderizan `#` ni `` ` ``).

Ambos formatos se derivan **exclusivamente de `ReportData`** (read-only sobre
la BD, igual que los exportadores existentes): cero red, cero LLM, cero
lectura de archivos de assets. No cambia ningún contrato de datos existente;
se añade un valor al enum `ExportFormat` y dos exportadores nuevos.

Qué aporta de producto:

- El hunter pega el finding en la pestaña "New report" del programa sin
  reescribir nada: plantilla en texto plano con todos los campos de la ficha
  (evidencia, impacto, repro no explotativa, remediación).
- El CSV da una vista tabular del run para triage, hojas de cálculo y para
  futuras integraciones de dashboard, sin exponer metadata cruda fuera del
  contrato del reporte.

Preservación de invariantes:

- **Cero bytes de archivos** (regla 3): las columnas/campos son los del
  contrato del reporte (snippets ya sanitizados, URLs, prosa), nunca los
  archivos de los assets.
- **Sin red** (regla 1): exportar es escribir un archivo local. **No hay
  auto-envío** a HackerOne/Bugcrowd (la feature 04 lo excluye explícitamente).
- **Enums en minúsculas** en CSV/JSON (el texto plain de la plantilla puede
  mostrar severidad en Title Case, capa de presentación).
- **El export no inventa**: los datos vienen de `ReportData`, que es el
  mismo que ya validan los exportadores de TASK-04. Los campos vacíos se
  renderizan como `Not generated (heuristic baseline)` (mismo placeholder),
  nunca se rellenan con texto nuevo.

---

## 2. Subtareas

### 18.1 Contratos

**Valor nuevo en el enum `ExportFormat`** (en `metatracer/services/orchestrator.py`):

| Enum | Valores |
| :--- | :--- |
| `ExportFormat` | `md` \| `json` \| `html` \| **`csv`** \| **`bounty`** \| `all` |

- `csv` → fichero `.csv` (RFC 4180, stdlib `csv`).
- `bounty` → fichero `.txt` (escrito por el exportador de plantilla).
- `all` ahora genera **md + json + html + csv + bounty**.

**Sin cambios** en los enums cerrados de datos (`finding_type`, `severity`,
`confidence`, etc.). No se añade valor a ningún otro contrato.

### 18.2 Exportador CSV (`metatracer/reports/csv_exporter.py`)

Nuevo módulo en `metatracer/reports/`, **0 dependencias nuevas** (stdlib
`csv`):

- `CSV_COLUMNS`: las *mismas* columnas que el JSON de TASK-04 (subtask
  4.3.2), una por finding:
  `run_id, target, severity, finding_type, confidence, asset_url, field,
  evidence, impact, explanation, remediation` (en este orden).
  - `severity`: minúsculas; vacío (`""`) si el finding está sin clasificar
    (NULL) — no usar la palabra "unclassified" en el CSV para no romper el
    parseo por severidad en hojas de cálculo (el Markdown sí la muestra).
  - `finding_type`, `confidence`: minúsculas (enums del contrato).
  - `evidence`: el snippet persistido byte-a-byte (trim de whitespace),
    igual que el JSON.
  - `impact`/`explanation`/`remediation`: prosa o `Not generated
    (heuristic baseline)`.
- `class CsvReportExporter`:
  - `export(self, data: ReportData) -> Path` — escribe
    `reports/metatracer-{slug}-{run_id_short}-{ts}.csv` (mismo
    `report_filename_stem`), con **cabecera** y una fila por finding.
  - `csv.DictWriter` con `quoting=csv.QUOTE_MINIMAL` (RFC 4180), saltos de
    línea `\r\n`, encoding UTF-8 con BOM (`utf-8-sig`) para que Excel
    abra UTF-8 sin mojibake. Cero red/LLM.
  - Run sin findings: fichero válido **con cabecera y 0 filas** (no error).

### 18.3 Exportador plantilla bounty (`metatracer/reports/bounty.py`)

Nuevo módulo en `metatracer/reports/`, **0 dependencias nuevas** (stdlib):

- `render_bounty(data: ReportData) -> str` — escribe **un** write-up por
  finding en **texto plano** (UTF-8, sin markdown, inglés — plataformas de
  bounty). Formato por finding:

```text
=== Finding 1/3 ===
Title: Internal Path Disclosure in Public PDF
Severity: High
Finding type: Internal Path
Affected asset: https://target.com/doc.pdf
Metadata field: XMP:CreatorTool
Evidence: C:\Users\mrodriguez\Workspace\FinancialApp\export_v2.pdf
Impact: Reveals internal username (mrodriguez) ...
Explanation: ...
Reproduction (non-exploitative):
1. Download the public file: curl -O https://target.com/doc.pdf
2. Inspect metadata: exiftool -CreatorTool doc.pdf
Remediation: Strip workstation paths in the document export pipeline ...
```

- Los **campos igual que la ficha de TASK-04** (subtask 4.2): Title,
  Severity (Title Case), Affected asset, Finding type (etiqueta humana),
  Metadata field, Evidence (byte-a-byte), Impact, Explanation,
  Reproduction (lista numerada) y Remediation. Placeholder
  `Not generated (heuristic baseline)` para prosa vacía (igual que Markdown).
- Separador entre findings: línea en blanco + línea `---`.
- Un run vacío produce un fichero con el summary y `No findings.` (válido,
  no error). Encabezado opcional con target/scope/run_id y línea de
  compliance (recuerda autorización in-scope) — el texto del programa puede
  requerirlo; ver criterios abajo.
- `class BountyExporter` — `export(self, data) -> Path` escribe
  `reports/metatracer-{slug}-{run_id_short}-{ts}.txt`.

### 18.4 Orquestador + CLI + API (wiring)

- **Orquestador** (`services/orchestrator.py`):
  - `ExportFormat` gana `csv` y `bounty`.
  - En `_export_reports`, las ramas:
    - `formats in (ExportFormat.csv, ExportFormat.all)` → `paths["csv"] = CsvReportExporter(output_dir).export(data)`
    - `formats in (ExportFormat.bounty, ExportFormat.all)` → `paths["bounty"] = BountyExporter(output_dir).export(data)`
  - `export_report`/`scan` no cambian de firma: `format=all` ya cubre todo.
- **CLI** (`cli/main.py`): `scan`/`report` con `--format csv|bounty` (el
  enum Typer lo acepta sin tocar código; actualizar el `help` de `--format`).
- **API** (`api/runs.py`): `GET /api/runs/{id}/export?format=csv|bounty` →
  `FileResponse` con `"text/csv"` / `"text/plain"` (añadir al mapa
  `_EXPORT_MEDIA_TYPES`). Botones de descarga en `templates/run.html`
  (exportar CSV y TXT bounty), mismo patrón que md/json/html.

### 18.5 Safety y persistencia

- Los exportadores **solo leen** `ReportData` (read-only); no tocan la BD de
  escritura, no hay red, no hay LLM.
- Los snippets salen como ya están en el reporte (sanitizados por el pipeline,
  ~150 chars); el CSV/plain no re-sanitiza (el dato ya está limpio en la BD).
- CSV y txt pueden contener datos personales (emails, GPS) porque son la
  evidencia del finding; el operador controla el archivo (igual que el
  Markdown/JSON). Se mantiene el compliance notice en la plantilla bounty.
- **No es un canal de egreso automático**: el archivo se genera en
  `reports/` local; no se envía a ningún servicio (auto-envío queda fuera de
  alcance, feature 04).

---

## 3. Fuera de alcance

- **Auto-envío a HackerOne/Bugcrowd/Intigriti** (feature 04: "No
  planificado"). Esta task solo produce archivos.
- PDF nativo (`reportlab` sería runtime; el HTML de v1.1 se imprime a PDF).
- Traducción del write-up a español (los reportes exportados son en inglés).
- Formatos propietarios de cada plataforma (XML/JSON de API de HackerOne):
  solo texto plano pegable.
- Plantillas por-plataforma diferenciadas (un solo formato `bounty`
  genérico; los campos son los que piden las tres).
- Campo de "Vulnerability type" por plataforma / CWE (requiere mapeo externo
  que no aporta el pipeline).

---

## 4. Tests mínimos

- `tests/unit/test_report_builder.py` (ampliado):
  - `ExportFormat.csv`/`bounty` aceptados por el enum.
  - `CsvReportExporter.export` escribe cabecera + una fila por finding con
    las columnas del contrato; run vacío → cabecera y 0 filas (válido).
  - `render_bounty` produce un bloque por finding con todos los campos de la
    ficha (Title, Severity, Evidence byte-a-byte, Reproduction), en texto
    plano sin `#`/`` ` ``; run vacío → `No findings.`.
- `tests/integration/test_cli_scan_help.py` (o equivalente):
  - `report --format csv` y `--format bounty` generan `.csv` y `.txt`.
  - `GET /api/runs/{id}/export?format=csv|bounty` devuelve 200 con el
    content-type correcto.
- `pytest -m "not e2e"` en verde y `ruff check src tests` limpio,
  validado con el guardrail de TASK-16 (`scripts/ci-check.ps1`).

---

## 5. Criterios de aceptación (DoD)

- [x] `metatracer report RUN_ID --format csv` produce un `.csv` con cabecera
      y una fila por finding, enums en minúsculas, severidad vacía si NULL.
- [x] `metatracer report RUN_ID --format bounty` produce un `.txt` que un
      triager puede pegar en HackerOne/Bugcrowd/Intigriti con la ficha
      completa y sin marcas de markdown.
- [x] `--format all` escribe **md + json + html + csv + bounty**.
- [x] `GET /api/runs/{id}/export?format=csv|bounty` descarga los ficheros con
      los content-types correctos.
- [x] Evidence en CSV/plain = evidence persistida (byte-a-byte, trim).
- [x] Run vacío → CSV con cabecera/0 filas y TXT con `No findings.` (válidos).
- [x] Cero dependencias nuevas; cero red; cero LLM; sin auto-envío.
- [x] Suite completa en verde y `ruff` limpio (guardrail TASK-16).