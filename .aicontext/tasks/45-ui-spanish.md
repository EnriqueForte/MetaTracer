# TASK-45: Web UI en español

**Módulo:** `web/`  
**Spec:** [specs/45-ui-spanish.md](../../specs/45-ui-spanish.md)  
**Dependencias:** TASK-42, TASK-43  
**Agentes:** `v2-ui-engineer`  
**Estado:** **Cerrada 2026-11-11.**

## 1. Objetivo técnico

Sustituir el copy de presentación de Web V2 por español. Sin paquete i18n nuevo.
Enums y query params intactos. `lang="es"` en el documento.

## 2. Subtareas

- Etiquetas compartidas (estado de run, severidad, confianza, triage, tipo de finding, etapas SSE).
- Shell, paleta, scan, historial, dashboard, workspace del run, findings, investigations, auth, admin.
- Tests Vitest y Playwright alineados al copy español.
- Contratos de idioma: UI web en español; CLI y reportes exportados siguen en inglés.

## 3. Fuera de alcance

CLI. Cuerpos de reporte. FastAPI `detail`. Rediseño para principiantes.

## 4. DoD

- [x] `html lang="es"`; ninguna pantalla de `web/src` muestra copy de producto en inglés
- [x] Vitest de `web/` verde; e2e de wizard/auth usan selectores en español
- [x] Exportadores de `reports/` sin cambios de idioma
- [x] Spec 45 closed al terminar; MEMORY y backlog actualizados
