# TASK-43: UI de investigations

**Módulo:** Web V2 (`web/`)  
**Spec:** [specs/43-ui-investigations.md](../../specs/43-ui-investigations.md)  
**Dependencias:** TASK-36 (API/CLI)  
**Agente:** `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-05.**

## 1. Objetivo

Listar y abrir investigations en Next. Agrupar runs desde esas superficies. Correlaciones y sugerencias de triage siguen en la vista del run (ya existen); no se auto-aplican. Texto, no HTML del target. Tipos desde OpenAPI.

## 2. Subtareas

- Ruta `/investigations` (listado + create operator) y `/investigations/[id]` (runs, close).
- Nav Research + command palette.
- El nombre en el run header enlaza al grupo.
- Viewers leen; mutaciones solo operator (403 del API).
- Tests Vitest: lista, empty, hide create para viewer, close, enlace al run.

## 3. Fuera de alcance

Grafo OSINT. API nueva de correlaciones por investigation. Spec 42 (triage masivo).

## 4. DoD

- [x] Listado y ficha con runs como `Link` a `/runs/{id}`
- [x] Close no aplica triage
- [x] Nav + palette
- [x] Tests verdes
