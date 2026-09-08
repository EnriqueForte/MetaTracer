# TASK-04: Motor de Generación y Exportación de Reportes

**Módulo:** Generación de Reportes  
**Referencia PRD:** [Generación de Reportes](../features/04-report-generation.md)  
**Dependencias:** [TASK-02](02-specific-detection.md), [TASK-03](03-risk-classification.md)  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Consolidar findings ya clasificados en write-ups listos para Bug Bounty. Exportar **Markdown** y **JSON** en **inglés**.

Esta task **no** depende de LangGraph. Si el agente aún no ha corrido, el reporte usa las plantillas del heurístico. Campos vacíos no rompen la exportación: se muestra `Not generated (heuristic baseline)` o el texto de plantilla, nunca un crash.

---

## 2. Subtareas Detalladas

### Subtarea 4.1: `ReportBuilder`

- **4.1.1. Orden:**
  1. Severity: `critical` (5) → `info` (1). Findings con `severity IS NULL` van al final (tratarlos como no clasificados, no como info).
  2. Confidence: `high` → `low`.
  3. `Asset.discovered_at` ascendente.
- **4.1.2. Cabecera:**
  - Título: `MetaTracer Security Report`
  - Target, scope confirmado, `run_id`, timestamp UTC ISO-8601, `reasoning_depth`
  - Executive summary: `Total assets: X | Critical: A | High: B | Medium: C | Low: D | Info: E | Unclassified: N`
  - Párrafo corto de higiene de metadata (heurístico o, si existe, el summary del nodo de TASK-05). Implementación: `ReportBuilder` lee `Run.executive_summary`; si está relleno lo usa, salvo en run vacío (la frase fija de 4.1.3 siempre gana).
  - **Scope & Compliance Notice:** auditoría pasiva in-scope sobre documentos públicos; no es un test de explotación.
- **4.1.3. Run vacío:** archivo válido: `No sensitive metadata was identified in the N document(s) analyzed.` No fallar.

---

### Subtarea 4.2: Ficha por finding (inglés)

Cada entrada, en este orden:

1. **Title** — una línea (`Internal Path Disclosure in Public PDF`). Si TASK-05 guardó `Finding.title`, se usa ese (colapsado a una línea); si no, plantilla por tipo + contexto del asset.
2. **Severity** — Title Case
3. **Affected asset** — `source_url` / `final_url`, content-type
4. **Finding type** — etiqueta humana (`GPS / Coordinates`, `Email`, `Internal Path`, `Software Version`, `Debug Comment`)
5. **Evidence** — `field_source` + snippet en bloque de código. Debe coincidir byte-a-byte (salvo whitespace trim) con el finding persistido
6. **Impact**
7. **Explanation** — prosa del agente o plantilla
8. **Reproduction (non-exploitative)** — p. ej. `curl` del URL público + `exiftool` / `pdfinfo`. Cero payloads
9. **Remediation** — strip EXIF, sanitizar export, regenerar, política de publicación

No incluir bytes del archivo ni thumbnails.

---

### Subtarea 4.3: Exportadores

**Ubicación:** `reports/metatracer-{slug-target}-{run_id_short}-{YYYYMMDDTHHMMSSZ}.md` (y `.json`). Slug: dominio sanitizado `[a-z0-9.-]`. Override con `--output-dir`.

No hace falta tabla `Report` en SQLite en el MVP: se regenera desde findings. Si se exporta dos veces, se sobrescribe o se crea un archivo nuevo con timestamp (preferir timestamp para no perder copias).

#### 4.3.1. `MarkdownReportExporter`

GFM. Severidad como heading: `### [High] Internal Path Disclosure in Corporate Document`.

````markdown
### [High] Internal Path Disclosure in Corporate Document

- **Target URL:** `https://target.com/annual-report.pdf`
- **Metadata Field:** `XMP:CreatorTool`
- **Evidence:**
  ```text
  C:\Users\mrodriguez\Workspace\FinancialApp\export_v2.pdf
  ```
- **Impact:** Reveals internal username (`mrodriguez`) and local directory structure.
- **Reproduction Steps:**
  1. Download the public file: `curl -O https://target.com/annual-report.pdf`
  2. Inspect metadata: `exiftool -CreatorTool annual-report.pdf`
- **Remediation:** Strip workstation paths in the document export pipeline before publishing.
````

#### 4.3.2. `JsonReportExporter`

Esquema Pydantic. Enums en **minúsculas**. `reproduction_steps` como `list[str]`.

```json
{
  "metatracer_version": "1.0.0",
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "target": "target.com",
  "scope": ["target.com"],
  "generated_at": "2026-08-29T18:00:00Z",
  "reasoning_depth": "standard",
  "summary": {
    "total_assets_scanned": 15,
    "total_findings": 4,
    "severity_counts": {
      "critical": 0,
      "high": 1,
      "medium": 2,
      "low": 1,
      "info": 0,
      "unclassified": 0
    }
  },
  "findings": [
    {
      "id": "...",
      "type": "internal_path",
      "severity": "high",
      "confidence": "high",
      "asset_url": "https://target.com/doc.pdf",
      "field": "XMP:CreatorTool",
      "evidence": "C:\\Users\\mrodriguez\\...",
      "impact": "...",
      "explanation": "...",
      "remediation": "...",
      "reproduction_steps": ["..."]
    }
  ],
  "compliance_notice": "This scan was limited to the confirmed in-scope public documents. Reproduction is inspection-only."
}
```

Validar con `model_validate` / `model_dump(mode="json")` antes de escribir.

---

## 3. Fuera de alcance de esta tarea

- Auto-envío a HackerOne/Bugcrowd.
- Filtros avanzados, historial de exportaciones, PDF/HTML extra — cubierto por [TASK-08](08-usability.md) (v1.1, completada). PDF nativo sigue fuera.
- Traducir el reporte al español.
- Llamar al LLM para “bonitar” el reporte (eso es TASK-05, antes de exportar).

---

## 4. Tests mínimos

`tests/unit/test_report_builder.py`:

- Orden Critical → Info
- Run sin findings → Markdown y JSON válidos
- JSON pasa el schema Pydantic
- Evidence en el export = evidence del finding
- Finding sin prosa de agente → archivo válido (plantilla o placeholder)

---

## 5. Criterios de Aceptación (DoD)

- [x] Hallazgos ordenados de mayor a menor severidad; `null` al final.
- [x] Markdown copiable a un programa de bounty, con todos los campos de la ficha.
- [x] JSON válido según schema; enums en minúsculas.
- [x] Run vacío → reporte válido, no archivo vacío/corrupto.
- [x] Evidence del reporte = evidence persistida.
- [x] Incluye aviso de scope / uso responsable.
- [x] Exportar funciona con findings solo-heurísticos (TASK-05 no ejecutado).
