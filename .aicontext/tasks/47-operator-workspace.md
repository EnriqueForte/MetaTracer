# TASK-47: Workspace de operador (UI)

**Módulo:** `web/` (hallazgos, nav, paleta, cobertura, integraciones, usuarios) · `services/workspace.py` (`by_content_type`)  
**Spec:** [specs/47-operator-workspace.md](../../specs/47-operator-workspace.md)  
**Dependencias:** TASK-42, TASK-45, design-system-v2  
**Agentes:** `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-12.**

## 1. Objetivo técnico

Cerrar la deuda de operador: hallazgos en split pane como Activos/Metadatos, atajos `[`/`]`, Comparar en nav Research, Integraciones en paleta, rollups MIME y valores `author_string`/email, chips de procedencia en la ficha, estados Empty/Loading/Error compartidos.

## 2. Subtareas

- `SplitPane`: `[` ensancha el panel, `]` lo estrecha (también en el separador). Hallazgos: split ≥1024px, `FindingSheet` por debajo.
- Nav Investigación: Comparar (`/runs/compare`). Paleta: Integraciones (operador).
- Cobertura: `by_content_type` (MIME) con barras CSS. Tabla agrupada de `email` y `author_string` (no grafo).
- Ficha de finding: `LayerChip` Observado (evidencia) / Inferido (análisis de IA).
- Integraciones, Usuarios, Cobertura: `EmptyState` / `LoadingState` / `ErrorState`.
- Regenerar OpenAPI / `schema.d.ts`.

## 3. Fuera de alcance

Recharts, MapLibre, grafos, spec 46 búsqueda, `finding_type` nuevo, CORS.

## 4. DoD

- [x] Split de hallazgos en desktop; Sheet en viewport estrecho
- [x] `[` / `]` redimensionan el panel
- [x] Comparar en nav; Integraciones en paleta operador
- [x] MIME en cobertura; tabla email/autor
- [x] LayerChip en la ficha
- [x] Estados compartidos en las tres vistas
- [x] Spec 47 closed al terminar
