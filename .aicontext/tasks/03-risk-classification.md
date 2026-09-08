# TASK-03: Clasificación de Riesgo y Rúbrica de Severidad

**Módulo:** Clasificación de Riesgo  
**Referencia PRD:** [Clasificación de Riesgo](../features/03-risk-classification.md)  
**Dependencias:** [TASK-00](00-architecture-and-safety.md), [TASK-02](02-specific-detection.md)  
**Estado:** Completada  

> Implementación en `src/metatracer/classification/` (`rubric`, `templates`, `anchor`, `classifier`, `pipeline`). Paquete añadido al layout de TASK-00: la lista original no contemplaba un hogar para el clasificador; se ubica como paquete hermano de `detectors/`. Tests en `tests/unit/test_risk_classifier.py`.

---

## 1. Objetivo Técnico

Contrato de severidad (`critical|high|medium|low|info`) anclado en evidencia. Fuente de verdad para:

1. El clasificador heurístico (offline, tests, fallback).
2. Los prompts y el validador de TASK-05.

El heurístico debe ser **determinista, sin red y sin OSINT**. No geocodifica GPS. No consulta CVEs. No infiere cargos (“CEO”) ni viviendas.

---

## 2. Subtareas Detalladas

### Subtarea 3.1: Rúbrica contextual

Usar esta tabla en código (constantes o YAML cargado en tests) y en el system prompt del agente.

| Nivel | Cuándo aplica | Ejemplos válidos | Lo que **no** basta |
| :--- | :--- | :--- | :--- |
| `critical` | Secreto o credencial **en el snippet**, o GPS **más** texto que identifique vivienda/persona/instalación no pública | `password=`, `api_key=`, `BEGIN PRIVATE KEY`, `TODO: token=ghp_...` | Un GPS solo; la palabra `CONFIDENTIAL` sola |
| `high` | Path con username o UNC interno; GPS preciso **sin** más contexto | `C:\Users\jdoe\...`, `\\CORP-DC01\share\...`, coordenadas válidas | `/var/www/html` sin usuario |
| `medium` | Email nominal corporativo; debug con proyecto/ticket/staging; path Unix genérico de deploy | `nombre.apellido@empresa.com`, `JIRA-8812`, `/var/www/intranet` | Email `@adobe.com` (no debería existir como finding) |
| `low` | Versión de software con número, sin más | `Apache FOP 2.4`, `Microsoft Word 16.0` | Afirmar “vulnerable a CVE-…” sin evidencia en el payload |
| `info` | Evidencia vacía, genérica o débil que el detector dejó pasar | Keyword `DRAFT` aislada, cadenas ambiguas | Inflar a high “por si acaso” |

Dos findings del mismo tipo **pueden** diferir de nivel si el snippet difiere. El contexto sale del snippet y de `field_source` / `content_type` / dominio, no de conocimiento externo.

---

### Subtarea 3.2: Anclaje anti-alucinación (también usado por TASK-05)

- **3.2.1. Existencia:** si `evidence_snippet` está vacío, no es substring de ningún `RawMetadataItem.value` de ese asset, o no cuadra con el tipo → forzar `info` (o no clasificar por encima de `info`).
- **3.2.2. Downgrade:** ante ambigüedad, un nivel menos. Prohibido subir severidad sin texto que lo justifique.
- **3.2.3. Techos del heurístico (obligatorios):**
  - GPS → máximo `high` (nunca `critical` por coordenadas solas).
  - `software_version` → máximo `low` (el nombre `wkhtmltopdf` no convierte el finding en “RCE”; eso sería inventar exploitabilidad).
  - Email → máximo `medium`.
  - `internal_path` con username/UNC → `high`; `/var/www` sin usuario → `medium`.
  - `debug_comment` con `password|secret|api[_-]?key|token|credential` en el snippet → `critical`; resto fuerte → `medium`; keywords débiles → `low` o `info`.

---

### Subtarea 3.3: `HeuristicRiskClassifier`

```python
def classify_heuristically(finding: Finding, asset: Asset | None = None) -> SeverityAssessment:
    ...
```

`SeverityAssessment`: `severity`, `justification`, `impact_analysis`, `remediation_advice`, `reproduction_steps` (plantillas fijas en inglés, porque alimentan el reporte).

- **3.3.1.** Sin I/O. Mismos inputs → misma salida.
- **3.3.2.** Plantillas por tipo+nivel: una frase de impacto y 1–3 pasos de remediación (strip EXIF, sanitizar export PDF, regenerar, etc.). Repro no explotativo: `exiftool` / `pdfinfo` sobre el archivo **público**; `{tool}=curl` cuando `field_source` empieza por `http:` / `html:` / `js:` o el content-type es HTML/JS ([TASK-09](09-source-expansion.md)).
- **3.3.3.** Escribir `severity` y textos de plantilla en el `Finding`. `agent_model_used` se deja vacío (TASK-05 pondrá `heuristic-fallback` solo cuando se active el fallback). En el flujo feliz de slice 3, TASK-05 puede **sobrescribir** justificación/impacto; no puede sobrescribir evidencia. Si TASK-05 no corre, estas plantillas son el contenido del reporte.

Orden de pipeline previsto:

1. Detectores (TASK-02) → findings sin severity.
2. Heurístico (esta task) → severity baseline + plantillas.
3. Agente (TASK-05) → puede ajustar severity **dentro de la rúbrica** y reescribir prosa; el guard solo puede **bajar** o rechazar, no subir por encima del techo de la rúbrica si la evidencia no cambia.

---

## 3. Fuera de alcance de esta tarea

- CVSS, tablas de bounty, envío a plataformas.
- Geocoding, WHOIS, búsqueda de CVEs, fingerprint de persona.
- Implementar LangGraph (TASK-05).

---

## 4. Tests mínimos

`tests/unit/test_risk_classifier.py`:

- Path `C:\Users\admin\SecretProject\` → `high`
- GPS válido → `high` (nunca `critical`)
- Email corporativo → `medium`
- Debug con `api_key` → `critical`
- `DRAFT` débil → `low` o `info`
- Snippet vacío → `info`
- Misma entrada dos veces → misma severity
- Versión de software → `low`, justificación **sin** CVE inventado

---

## 5. Criterios de Aceptación (DoD)

- [x] Todo finding clasificado tiene exactamente una severity del set de cinco.
- [x] Path de usuario Windows → mínimo `high`.
- [x] GPS válido → `high` en heurístico (no `critical`).
- [x] Evidencia vacía o genérica → `info` o `low`.
- [x] El heurístico no realiza I/O de red ni lee archivos binarios.
- [x] Las plantillas de repro no incluyen payloads de exploit.
