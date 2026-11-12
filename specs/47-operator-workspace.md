# Spec 47 — Workspace de operador (UI)

**Estado:** closed (2026-11-12)  
**Agente previsto:** `v2-ui-engineer` · contratos visuales: `ui-architect` si hace falta
aclarar split pane  
**Contrato visual:** `.aicontext/ui/design-system-v2.md`  
**Skill al abrir:** `metatracer-ui`  
**Task:** [TASK-47](../.aicontext/tasks/47-operator-workspace.md)

## Intención

Cerrar deuda de operador post-specs 42/43/45 **sin** inventar producto ni librerías de
gráficos. El design system pide workspace de dos columnas y atajos `[`/`]`; hallazgos
siguen en `FindingSheet` bajo 1024px. Comparar dos runs existe (`/runs/compare`) pero no está en
nav Research; Integraciones está en nav y no en la paleta.

## Alcance

- Hallazgos en **split pane** (paridad con Activos/Metadatos); atajos `[` / `]`.
- Nav Research: enlace a Comparar. Paleta: Integraciones.
- Rollups (tablas/barras CSS existentes, no Recharts): histograma `content_type` /
  MIME en cobertura del run; tabla agrupada de `author_string` y emails
  compartidos (texto; `correlation.kind` ya emitido — no es identidad).
- Chips de procedencia Observed / Inferred / External en la ficha de finding
  (escala distinta de severity; design-system §1).
- Empty/loading/error con primitivos compartidos en Integraciones, Usuarios, Cobertura.

## Fuera de alcance

Recharts, MapLibre, tiles CDN, grafos decorativos. Rediseño pedagógico (leftover spec 45).
Investigations nuevas. Búsqueda global (spec 46). i18n bilingüe. Jinja/Alpine.

## Dependencias

Specs 42/43/45/46 closed.
