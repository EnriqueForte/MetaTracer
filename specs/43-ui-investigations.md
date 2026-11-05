# Spec 43 — UI de investigations

**Estado:** closed  
**Task:** [`.aicontext/tasks/43-ui-investigations.md`](../.aicontext/tasks/43-ui-investigations.md)  
**Agente:** `v2-ui-engineer`  
**Depende de:** spec 36 closed (API).

## Intención

Superficies Next en `web/` para agrupar runs y ver correlaciones por `correlation.kind`.
Sugerencias de triage de otro run: visibles, **nunca auto-aplicadas**. Texto, no HTML del target.
Un origen; tipos desde OpenAPI regenerado.

## Fuera de alcance

Grafo “OSINT” con nodos de identidad. Mapa que infiera domicilio. Implementar 36 en el cliente.

## Dependencias

Spec 36 + TASK-36. Skill `metatracer-ui`. Contrato `design-system-v2.md`.
