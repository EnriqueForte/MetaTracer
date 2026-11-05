---
name: report-engine
description: Motor de reportes de MetaTracer (ReportBuilder, orden severity, ficha de finding en inglés, exportadores Markdown/JSON/HTML/CSV/Bounty y nomenclatura de ficheros). Usar al tocar reports/builder.py, markdown.py, json_exporter.py, html.py, csv_exporter.py, bounty.py, filters.py o schemas.py, y al añadir o cambiar un campo del reporte.
---

# Motor de reportes

Un solo `ReportData` neutral de presentación alimenta todos los exportadores.
Fuente: `.aicontext/tasks/04-report-generation.md`, `08-usability.md`, `18-exports-bounty.md`.

## Flujo

```
Finding (BD) → ReportBuilder → ReportData ─┬─→ MarkdownReportExporter
                                           ├─→ JsonReportExporter (schema validado)
                                           ├─→ HtmlReportExporter
                                           ├─→ CsvReportExporter
                                           └─→ BountyExporter (texto plano)
```

No hay tabla `Report` en BD: el reporte **se regenera** desde los findings.
`ReportBuilder` resuelve prosa y contexto del asset; los exportadores solo
formatean.

## Orden y cabecera

- Orden de findings: **critical → info**, `NULL` al final; desempate por
  confidence y luego `discovered_at`. Usa `_SEVERITY_ORDER` (critical 5 … info 1,
  NULL 0). **No** es `SEVERITY_RANK` de la rúbrica (0…4): mismo espíritu, otra tabla.
- Cabecera: título, target, scope, `run_id`, timestamp UTC, `reasoning_depth`,
  resumen ejecutivo y **Scope & Compliance Notice** (`COMPLIANCE_NOTICE`).
- Run vacío → archivo **válido** con mensaje de cero hallazgos (nunca crash).

## Ficha de un finding (inglés, orden fijo)

`Title` → `Severity` → (`Triage` solo si ≠ `open`) → `Finding type` →
`Affected asset` → `source`/content-type → `Field` → `Evidence` →
`Impact` → `Explanation` → `Reproduction steps` → `Remediation`.

- Severity en **Title Case** (`High`, `Critical`) en la capa de presentación.
- Prosa vacía → `Not generated (heuristic baseline)` (`PROSE_PLACEHOLDER`).
  Nunca un crash, y nunca presentar plantilla como análisis del agente.
- `type_label` humano: `GPS / Coordinates`, `Email`, `Internal Path`,
  `Software Version`, `Debug Comment`.

## Evidencia hostil (amenaza 11)

El snippet lo escribió el target y puede contener backticks, saltos de línea,
`#` al inicio de línea o corchetes.

- Markdown: bloque cercado `text` cuyo **fence** es
  ``"`" * max(3, longest_backtick_run(evidence) + 1)``; solo se indenta la
  línea del fence, **el contenido va byte a byte** como se persistió.
- Prosa inline: `_escape_inline` colapsa a una línea y escapa `#`, `[`, `]`.
- Prohibido romper la evidencia "para que se vea mejor": se alteraría la prueba.

## Exportadores

- **Markdown**: GFM; heading `### [High] …`; ficha anterior.
- **JSON**: `ReportDocument` (Pydantic) validado con `model_dump`/`model_validate`
  antes de escribir; enums en minúsculas; `reproduction_steps: list[str]`;
  `compliance_notice`. Campos: `metatracer_version`, `run_id`, `target`, `scope`,
  `generated_at`, `reasoning_depth`, `summary`, `findings`, `compliance_notice`.
- **HTML**: el mismo `ReportData`, evidencia **escapada** (autoescape), cero
  dependencia runtime de PDF (se imprime si hace falta).
- **CSV**: RFC 4180 con BOM UTF-8; **una fila por finding**; columnas en
  `CSV_COLUMNS` (orden es contrato). Celdas que empiezan por `= + - @ \t \r`
  se prefijan con `'` (`neutralize_spreadsheet_formula`, TASK-27) — se prefija,
  no se recorta, para conservar la evidencia.
- **Bounty**: texto plano listo para pegar; sí incluye `Reproduction steps`
  (el CSV no, por las celdas multilínea).

## Nomenclatura y confinamiento

`metatracer-{slug-target}-{run_id_short}-{YYYYMMDDTHHMMSSZ}.{md|json|html|csv|txt}`.
El slug se sanea a `[a-z0-9-]` y la escritura queda **confinada** al directorio
de salida (amenaza 10: no escribir fuera de `reports/`).

## Redacción (`export.redaction`, TASK-39)

Solo el **fichero**. `apply_redaction` copia `ReportData`; no hay UPDATE a
`Finding`. API `GET /api/runs/{id}/export?redact=` y CLI `report --redact`
default **`none`**. La UI propone **`contacts`**.

| Modo | Qué reescribe |
| :--- | :--- |
| `none` | Nada (marca el campo `redaction`) |
| `contacts` | emails → `[redacted-email]` |
| `coordinates` | GPS / pares lat-lon → `[redacted-coordinates]` |
| `all` | ambos |

El Markdown declara: stored findings were not modified. Prohibido borrar
`evidence_snippet` en BD al exportar.

## Paridad entre exportadores (T4)

`tests/unit/test_report_schema_parity.py` fija el mapa `ReportFinding` ↔
`CSV_COLUMNS` y las asimetrías intencionadas (`id`, `reproduction_steps`).
**Campo nuevo ⇒ decisión explícita** en `_FIELD_TO_COLUMN` o `_JSON_ONLY`
(el test falla si no). `triage_status = false_positive` queda fuera de los
exports salvo inclusión explícita (`filter_findings`).

## Checklist

- [ ] Orden critical→info y NULL al final.
- [ ] Prosa vacía ⇒ `Not generated (heuristic baseline)`, sin crash.
- [ ] Evidencia byte a byte; fence dimensionado al backtick más largo.
- [ ] Sin `|safe` / `innerHTML` con datos del target (HTML).
- [ ] CSV: fórmula neutralizada; orden de `CSV_COLUMNS` intacto.
- [ ] Campo nuevo ⇒ mapa de paridad y schema JSON actualizados.
- [ ] Nombre de fichero saneado y dentro de `reports/`.
- [ ] Redacción: copia del fichero; default API/CLI `none`; UI `contacts`.
