# TASK-08: Usabilidad (v1.1)

**Módulo:** Interfaces + reportes + guard post-LLM  
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md), [Generación de reportes](../features/04-report-generation.md)  
**Dependencias:** TASK-00 … TASK-07 (MVP cerrado y validado)  
**Estado:** Completada  

---

## 1. Objetivo técnico

Hacer MetaTracer usable día a día sobre el pipeline ya existente: reabrir runs locales, filtrar hallazgos, exportar HTML y revisar un run desde la CLI sin repetir el scan.

No se abre un segundo runtime, no se añade autenticación, no se añade dependencia runtime. El dashboard de plataforma sigue siendo v2.0.

Insumo de la validación v1.0: el `EvidenceGuard` debe rechazar una propuesta cuya explicación cite un nivel de rúbrica distinto del asignado (run `0b12350a`).

---

## 2. Subtareas

### 8.1 Historial local

- `GET /api/runs` — lista newest-first: `run_id`, `status`, `target`, `scope`, contadores, timestamps. Query opcional `status=` y `limit=`.
- Página `GET /runs` (Web UI) + enlace en la cabecera. Clic abre `/runs/{run_id}` existente.
- CLI `list-runs` acepta `--status` y `--limit`. Sigue siendo historial local, no el dashboard v2.0.
- Vacío: mensaje claro, no error.

### 8.2 Filtros de findings

Helper compartido (API, CLI, tests): `severity`, `finding_type`, `confidence`, `q` (substring casefold sobre title, evidence, field, URLs). Enums en minúsculas.

- `GET /api/runs/{run_id}/findings` acepta los cuatro query params (además del `severity=` ya existente).
- Web UI: badges de tipo + campo de búsqueda, además de los de severidad. La tabla filtra en cliente sobre la lista completa (el export sigue siendo el run entero: un reporte enviable no se recorta por un filtro de exploración).
- CLI `show` aplica los mismos filtros al renderizar.

### 8.3 Export HTML + CLI `show`

- `ExportFormat.html`. `--format all` escribe md + json + html.
- HTML autónomo (stdlib `html.escape`, CSS mínimo inline, **inglés**). Mismo contenido que Markdown. Sin CDN, sin JS, sin bytes de assets.
- API `GET /api/runs/{id}/export?format=html`. Botón en la UI.
- `metatracer show RUN_ID` — tabla de findings + summary. Acepta el UUID completo **o** el prefijo de 8 caracteres que muestra `list-runs`. Colisión de prefijo → error. `report` usa el mismo resolvedor.

### 8.4 Coherencia texto↔severidad (guard)

Si `justification` cita explícitamente un nivel de rúbrica (`critical|high|medium|low|info`) distinto del `severity` final del guard, **rechazar** la propuesta: el nodo clasifica en fallback heurístico (la rúbrica es la fuente de verdad). El guard sigue sin poder subir severidad.

---

## 3. Fuera de alcance

- PDF nativo (haría runtime a `reportlab`; el hunter imprime el HTML).
- Dashboard multi-run, notificaciones, auth, SaaS (v2.0).
- Nuevos `finding_type` (p. ej. `author_name` — candidato posterior; v1.2 no lo añadió. Actualizar contratos primero).
- Evadir WAF / spoofing de UA.

---

## 4. Tests mínimos

- `tests/unit/test_finding_filters.py` — cada filtro + combinado + `q` casefold.
- `tests/unit/test_report_builder.py` — export HTML contiene evidencia escapada y el compliance notice.
- `tests/integration/test_api_scope.py` — `GET /api/runs` lista; findings filtrados por tipo.
- `tests/integration/test_cli_scan_help.py` — `show --help`; `list-runs --status`; prefijo ambiguo.
- `tests/agents/test_evidence_guard.py` — explicación "high-severity" + `severity=medium` → `rejected`.

---

## 5. Criterios de aceptación (DoD)

- [x] `/runs` lista los scans locales y reabre uno.
- [x] Filtros de tipo/severidad/búsqueda coinciden entre API y CLI `show`.
- [x] `metatracer show <8-char>` abre el mismo run que el UUID.
- [x] Export HTML del mismo run tiene los mismos findings/severidades que Markdown/JSON.
- [x] Guard rechaza justificación que cita otro nivel; el finding persiste con el heurístico.
- [x] Cero dependencias runtime nuevas.
