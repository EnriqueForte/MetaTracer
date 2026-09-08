# ADR-0011: Cabeceras HTTP por allowlist, nunca secretos

**Fecha:** 2026-09-06  
**Estado:** Aceptada (v1.2 / [TASK-09](../tasks/09-source-expansion.md))  
**Slice:** Expansión de fuentes

## Contexto

Toda descarga exitosa ya tiene cabeceras en el gateway. Persistirlo todo metería
`Set-Cookie`, `Authorization` y tokens de debug en SQLite y, más tarde, en un snippet
hacia el LLM. Persistirlo nada deja fuera `Server` / `X-Powered-By`, que son recon clásico
y disparan `software_version` sin parser nuevo.

## Decisión

Tras un asset `ok`, persistir **solo** la allowlist de recon (nombres ya en minúsculas):

`server`, `x-powered-by`, `x-aspnet-version`, `x-aspnetmvc-version`, `x-generator`,
`x-runtime`, `x-version`, `x-application-version`, `via`, `x-debug`, `x-debug-token`,
`x-sourcemap`, `sourcemap`, `x-backend-server`, `x-served-by`, `x-redirect-by`, `x-pingback`.

Denylist de defensa en profundidad, aunque no estén en la allowlist: `authorization`,
`proxy-authorization`, `cookie`, `set-cookie`, `www-authenticate`, `proxy-authenticate`.

Un asset `skipped`/`failed` no genera `RawMetadataItem` (tampoco de headers).
Cero dependencias nuevas: el mapa de cabeceras ya lo normaliza el gateway.

## Alternativas descartadas

- **Persistir todas las cabeceras “por si acaso”.** Viola minimización (amenaza 14) y la
  regla de cero secretos en logs/DB/LLM. CSP/CORS como finding son otro `finding_type`.
- **Allowlist en el LLM, no en persistencia.** Si el secreto llegó a SQLite, ya se perdió
  el control. El corte es antes de `sanitize_value`.

## Consecuencias

- `Server: nginx/1.18.0` → finding `software_version` con `field_source=http:server`.
- Cookies y Authorization no aparecen en `raw_metadata_item` aunque el servidor las envíe.
- Ampliar la allowlist es un cambio de producto (actualizar TASK-09 + este ADR), no un
  one-liner en un extractor.
