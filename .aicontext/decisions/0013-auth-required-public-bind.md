# ADR-0013: Auth obligatoria en bind público, con escape explícito

**Fecha:** 2026-10-03  
**Estado:** Aceptada (v3.2 / [TASK-27](../tasks/27-security-hardening-p0.md), P0-2)  
**Slice:** Hardening post-auditoría

## Contexto

La postura histórica era "auth opcional, protegida por el bind a loopback"
(`METATRACER_AUTH_ENABLED=false` por defecto). Pero la imagen Docker publica
`0.0.0.0:8000`: el mismo default exponía a la red la creación de scans,
webhooks (egreso a terceros) e importación de la knowledge base **sin
credenciales**. La protección era una propiedad de la topología, no del
producto, y una topología equivocada la anulaba en silencio.

## Decisión

`serve` **se niega a arrancar** en un bind no-loopback mientras la
autenticación esté desactivada (`core/bind_auth.py`,
`UnauthenticatedPublicBindError`). Dos salidas explícitas:

1. `METATRACER_AUTH_ENABLED=true` (camino recomendado).
2. `METATRACER_ALLOW_UNAUTHENTICATED_BIND=true`: escape **ruidoso** (WARNING en
   cada arranque) para despliegues que confían en un proxy/red delante.

El escape no relaja scope ni `NetworkSafetyGuard`: solo permite el bind.

Compose publica `0.0.0.0` y por eso fija `METATRACER_AUTH_ENABLED=true` por
defecto; si el `.env` del operador lo desactiva, el contenedor **sale**.

## Alternativas descartadas

- **Auth obligatoria siempre, también en loopback.** Rompe el flujo del hunter
  local (CLI + `serve` en su máquina) sin ganancia: el loopback ya no es alcanzable
  desde fuera de la máquina.
- **Detección automática por interfaz.** Implica adivinar la topología real
  (NAT, túnel, proxy) y fallar abierto cuando la detección se equivoca.
- **Fijar `0.0.0.0` como inseguro sin escape.** Deja sin salida los despliegues
  tras mTLS/proxy que ya autentican fuera del proceso.

## Consecuencias

- Un `docker compose up` con `.env` heredado de `.env.example` (auth `false`)
  **no arranca** hasta corregirlo: falla cerrado y el mensaje lo explica.
- El CLI local (`scan`, `watch`) sigue sin login: no abre socket.
- La decisión del operador queda visible en el log (WARNING) cuando usa el escape.

**Verificación:** `tests/unit/test_task27_security_hardening.py`,
`tests/integration/test_api_auth.py`.
