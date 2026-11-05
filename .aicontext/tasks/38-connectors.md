# TASK-38: Conectores de egreso (Fase 4)

**Módulo:** `connectors/`, `api/connectors.py`, Integrations UI  
**Spec:** [specs/38-connectors.md](../../specs/38-connectors.md)  
**Dependencias:** TASK-15 (webhooks / anti-SSRF de egreso)  
**Agentes:** `pipeline-engineer`, `ui-engineer`  
**Estado:** **Cerrada 2026-11-05.** RDAP / Wayback / Common Crawl y la UI ya estaban; esta slice fija `ConnectorStatus` y no construye el cliente HTTP si el conector está apagado.

## 1. Objetivo técnico

Egreso opcional a una **lista cerrada** de destinos. Un conector **apagado no abre socket**. `degraded` = 429 (o rate-limit equivalente) y **no tumba** un run (los conectores no forman parte del scan).

Valores `connector.status`: `disabled` \| `available` \| `degraded` \| `error`.

HMAC sigue en webhooks (TASK-15); estos conectores son GET HTTPS a hosts fijos, sin redirects, `trust_env=False`, `NetworkSafetyGuard`. No añaden hosts al scope.

## 2. Subtareas

### 38.1 Contrato SDD

- Spec 38 `closed`. `connector.status` deja de ser reserved.
- Destinos: `rdap`, `wayback`, `commoncrawl`. Uno nuevo = decisión de supply-chain.

### 38.2 Código

- `ConnectorStatus` en `db/models.py`.
- Lookup/search aceptan `client=None` cuando `enabled=False`.
- API no instancia `ProviderClient` si está apagado.
- Catálogo: `enabled` + `status` (`disabled`/`available` según el toggle).

### 38.3 Tests

- Disabled no toca la red aunque el handler fallaría; también con `client=None`.
- 429 → `degraded`. Redirects no se siguen.

## 3. Fuera de alcance

OAuth/SSO. Escanear el destino. Redis/ARQ. Bus de eventos. Descargar WARC/replay.

## 4. DoD

- [x] Apagado = sin socket
- [x] 429 = `degraded`, el run de scan no depende de esto
- [x] Tests de la slice verdes; ruff limpio
- [x] Spec 38 closed; MEMORY y backlog actualizados
