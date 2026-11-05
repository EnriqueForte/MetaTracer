# Spec 42 — UI del operador

**Estado:** closed (2026-11-05)  
**Agente previsto:** `v2-ui-engineer` · contratos visuales: `ui-architect` (V2) si hay rediseño  
**Contrato visual:** `.aicontext/ui/design-system-v2.md`  
**Task:** [TASK-42](../.aicontext/tasks/42-ui-operator.md)

## Intención

Reducir fricción diaria post-TASK-35, sin inventar producto:

- Triage **masivo** (TASK-35 lo dejó OOS): mismos estados, solo operador, CSRF, no mutar severity/evidencia.
- Densidad y deuda de paneles (`findings-panel`, virtualización si aún incompleta).
- Atajos / paleta: no romper a11y ni `prefers-reduced-motion`.

## Fuera de alcance

Pantallas de investigations (spec 43). Reintroducir Jinja/Alpine. Tiles de mapa por CDN.
SSO/2FA. CORS / segundo host.

## Dependencias

TASK-35 cerrado. Skill `metatracer-ui`.
