# ADR-0012: El gateway HTTP ignora los proxies del entorno

**Fecha:** 2026-10-03  
**Estado:** Aceptada (v3.2 / [TASK-27](../tasks/27-security-hardening-p0.md), P0-1)  
**Slice:** Hardening post-auditoría

## Contexto

`httpx.AsyncClient` usa `trust_env=True` por defecto: honra `HTTP_PROXY`,
`HTTPS_PROXY`, `ALL_PROXY` y `NO_PROXY`. Con un proxy configurado en la máquina,
el socket se abre contra **el proxy**, no contra el host validado. El
`NetworkSafetyGuard` resuelve y valida el hostname de la URL — pero el destino
TCP real es otro. Un operador (o malware en su equipo) puede apuntar el tráfico
a `127.0.0.1` o a una IP interna saltándose el control anti-SSRF.

El mismo patrón aparecía en el cliente de webhooks.

## Decisión

Todo cliente HTTP de la aplicación se construye con **`trust_env=False`**:

- `core/safety/http.py` (gateway único, `safe_httpx_request`).
- `api/webhooks.py` (cliente dedicado de egreso, HTTPS-only).

El guard se ejecuta inmediatamente antes del socket y el proxy ya no puede
redirigir la conexión a un destino que nunca se validó.

## Alternativas descartadas

- **Confiar en `NO_PROXY`.** Es configuración del entorno, no del producto: el
  atacante con control del entorno también controla `NO_PROXY`.
- **Validar la IP del proxy.** No sirve: el proxy reenvía a cualquier destino,
  así que su IP pública pasaría el guard y el destino real no se comprueba.
- **Documentar "no uses proxy".** Una regla que depende de que el usuario no
  haga algo es exactamente lo que prohíbe el perfil fail-closed.

## Consecuencias

- Escanear a través de un proxy corporativo deja de funcionar; es deliberado y
  coherente con "loopback/privadas bloqueadas" (`METATRACER_ALLOW_LOOPBACK` ya
  era solo-test).
- Cualquier cliente HTTP nuevo debe nacer con `trust_env=False`; el
  `safety-guardian` lo verifica como bloqueante.
- Sin cambio de dependencias.

**Verificación:** `tools` de barrido de `trust_env` en `src/`; test en
`tests/unit/test_task27_security_hardening.py`.
