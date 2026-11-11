# Spec 45 — UI en español

**Estado:** closed (2026-11-11)  
**Agente previsto:** `v2-ui-engineer`  
**Contrato visual:** `.aicontext/ui/design-system-v2.md`  
**Task:** [TASK-45](../.aicontext/tasks/45-ui-spanish.md)

## Intención

La Web UI (`web/`) se presenta en **español**: navegación, formularios, estados vacíos, avisos éticos, filtros, paleta y atajos. El objetivo es que un operador hispanohablante (incluido quien empieza en bug bounty) lea la herramienta en su idioma.

Los **valores de contrato** (enums en API, query strings, `finding_type`, `severity`, `triage_status`) siguen en minúsculas inglesas. Solo cambia la capa de presentación.

## Fuera de alcance

- Traducir reportes exportados (Markdown/JSON/HTML/CSV/Bounty): siguen en **inglés** para plataformas de bug bounty.
- CLI Typer, mensajes de log y `detail` de FastAPI.
- Rediseño pedagógico para principiantes (siguiente análisis, no esta slice).
- i18n bilingüe ni nueva dependencia (`next-intl`, etc.).
- Cambiar `html lang` a un locale mixto; el documento de la UI es `es`.

## Dependencias

Skill `metatracer-ui`. Contratos de idioma en `.aicontext/tasks/README.md` y `data-contracts.mdc`.
