# Spec 38 — Conectores (Fase 4)

**Estado:** closed (2026-11-05)  
**Agente previsto:** `pipeline-engineer` + `ui-engineer` (CRUD API)  
**Enum:** `connector.status` en `.aicontext/tasks/README.md`  
**Task:** [TASK-38](../.aicontext/tasks/38-connectors.md)

## Intención

Egreso opcional hacia destinos ya cubiertos en espíritu por webhooks (TASK-15): un conector
**apagado no abre socket**. `degraded` = 429 del proveedor y **no tumba** el run.

Reutilizar anti-SSRF de egreso y HMAC donde aplique (webhooks). Lista cerrada de destinos
(RDAP, Wayback CDX, Common Crawl index); cada destino nuevo es decisión de supply-chain /
producto.

El código (`connectors/`, `/api/connectors`, Integrations) ya estaba; TASK-38 fija el enum
`ConnectorStatus` y omite el cliente HTTP cuando el conector está disabled.

## Fuera de alcance

OAuth/SSO. Escanear activamente el destino. Redis/ARQ. Inventar un bus de eventos.

## Dependencias

TASK-15 webhooks. Skill `metatracer-platform` (sección conectores).
