---
name: metatracer-safety-rules
description: Implementa y revisa el Safety Core de MetaTracer (ScopeValidator, NetworkSafetyGuard anti-SSRF, wrapper HTTP seguro, confirmación de scope, logging seguro). Usar al escribir o modificar código de red/HTTP, redirects, validación de scope, rate limiting, logging o configuración de seguridad.
---

# MetaTracer Safety Core

Toda la red del proyecto pasa por aquí. Si escribes código que hace HTTP, aplica esto primero. Referencia completa: `.aicontext/tasks/00-architecture-and-safety.md` (subtarea 0.3) y `.aicontext/tasks/01-metadata-extraction.md` (subtarea 1.2).

## ScopeValidator

- Normalizar: quitar `http://`/`https://`, path, query, fragment y puerto. Lowercase. Quitar el punto final.
- Matching: `host == domain` **o** `host.endswith("." + domain)`. `evil-target.com` **no** matchea `target.com`.
- Wildcard `*.target.com` matchea subdominios, **no** el apex (salvo que el apex esté también en la lista).
- Sin Public Suffix List en el MVP: `foo.co.uk` se trata como dominio opaco (limitación documentada).
- Host no cubierto por `allowed_scope` → `OutOfScopeError` **antes** de cualquier petición.

## NetworkSafetyGuard (anti-SSRF)

Antes de cada petición: resolver DNS y comprobar **todas** las IPs (A y AAAA). Bloquear:

- Loopback: `127.0.0.0/8`, `::1`
- Unspecified: `0.0.0.0/8`, `::`
- RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Link-local: `169.254.0.0/16` (incluye metadata cloud `169.254.169.254`), `fe80::/10`
- CGNAT: `100.64.0.0/10`
- Unique local IPv6: `fc00::/7`
- Multicast: `224.0.0.0/4`, `ff00::/8`
- Reserved / documentation (TASK-32): `192.0.0.0/24`, `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `198.18.0.0/15`, `240.0.0.0/4`, `255.255.255.255/32`, `2001:db8::/32`, `100::/64`
- Non-canonical IPv4 (decimal dword, octal, hex) is refused before DNS

Lanzar `SecurityViolationError` **antes** de abrir el socket. Limitación TOCTOU/DNS-rebinding aceptada en el MVP: no hace falta pin de IP en el transporte, pero la guarda debe llamarse **inmediatamente antes** de cada request.

## Wrapper HTTP único (`safe_httpx_request`)

Todo cliente HTTP del proyecto (crawler incluido) pasa por este helper:

- `follow_redirects=False`. Seguir a mano **máximo 5 hops**; en cada hop, `ScopeValidator` + `NetworkSafetyGuard`. Hop fuera de scope → `RedirectOutOfScopeError`, asset `skipped`/`out_of_scope`, **no leer el body**.
- Timeouts: connect 10s, read 20s, pool 10s.
- `User-Agent: MetaTracer/1.0 (authorized security audit; +https://github.com/your-org/metatracer)`.
- Intentar `HEAD` para `Content-Length`/`Content-Type`; si 405/501/red vacía → `GET` con stream y aborto al superar `MAX_FILE_BYTES` (default 50 MB).
- `DomainRateLimiter`: default `RATE_LIMIT_RPS=2` (~500 ms mínimo por dominio) + semáforo global (~3 descargas simultáneas).

## Confirmación de scope

- `scope_confirmed=False` → `ScopeNotConfirmedError` en el orquestador y en cualquier API pública de scan.
- El scope **nunca** se infiere en silencio a partir del target. En CLI, sin `-y` hay prompt con default `N`.
- `METATRACER_ALLOW_LOOPBACK` default `false`. Solo tests lo activan (monkeypatch de Settings / env en el proceso de test). Nunca en Compose de producto ni documentado como feature de usuario.

## Excepciones (jerarquía `MetaTracerError`)

`OutOfScopeError`, `RedirectOutOfScopeError`, `SecurityViolationError`, `ScopeNotConfirmedError`, `ExtractionError`, `UnsupportedAssetError`, `AgentUnavailableError`.

## Logging seguro

TASK-00 (0.4.2) fija el **formato** del log (`logging` stdlib, timestamp UTC, nivel, logger,
`run_id` si hay contexto, sin `print` en librería). Esto fija **qué entra en el mensaje**: es la
mitigación de la amenaza 13 (log injection) y se aplica en todo el código, no solo en `core/`.

- **Nunca** se loguea: `LLM_API_KEY`, cabeceras de autorización, el prompt completo, bytes de
  archivo, ni el cuerpo de una respuesta HTTP.
- Un valor que escribió el target (un `RawMetadataItem.value`, una URL, un nombre de archivo)
  **no se interpola directo** en el mensaje. Va sanitizado y truncado, o mejor, como campo
  estructurado aparte.
- El sanitizado mínimo antes de loguear: sustituir `\r` y `\n` por espacios y cortar a ~150
  chars. Sin CRLF no hay líneas falsas; sin líneas falsas no hay entradas de log inventadas.
- Cuando haga falta más contexto, `logger.info("asset extraído", extra={"asset_id": ...})`, no
  una cadena formateada con el valor crudo.
- Los mensajes de error de un asset fallido se persisten en `error_message` (texto sanitizado),
  no se vuelcan enteros al log.

```python
# MAL: el valor del target rompe el log y puede inyectar líneas
logger.info(f"Metadata extraída: {raw_value}")

# BIEN: sanitizado y truncado antes de entrar en el mensaje
logger.info("Metadata extraída: %s", sanitize_for_log(raw_value))
```

## Checklist de revisión

- [ ] Ningún `httpx` crudo fuera del wrapper.
- [ ] Guard llamada inmediatamente antes de cada request (también por hop de redirect).
- [ ] Sin flag `--insecure` ni bypass activo por defecto.
- [ ] `ALLOW_LOOPBACK` solo aparece en tests y `.env.example` marcado como "test only".
- [ ] Las excepciones de safety abortan el run con mensaje claro; un asset fallido solo se marca y el run sigue.
- [ ] Ningún valor del target se interpola crudo en un mensaje de log (sin CRLF, truncado).
