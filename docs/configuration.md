# Configuración y privacidad

[Volver al README](../README.md)

## Configuración

Copia `.env.example` → `.env`. Todas las variables llevan el prefijo
`METATRACER_`.

| Variable | Nota |
| --- | --- |
| `METATRACER_DATABASE_URL` | SQLite por defecto; Postgres exige `postgresql+asyncpg://` |
| `METATRACER_LLM_*` | Vacío = solo heurística |
| `METATRACER_AUTH_ENABLED` | `true` en el clon (`./run.sh` / `MetaTracer.cmd` y `.env.example`): login y primer usuario. `false` solo si lo exportas. Un bind público exige auth |
| `METATRACER_ALLOW_LOOPBACK` | **Solo tests.** Fuera de pytest, `scan` / `serve` / `watch` no arrancan |

En localhost la CLI no pide login. Un bind a `0.0.0.0` sin auth se niega a
arrancar (salvo `METATRACER_ALLOW_UNAUTHENTICATED_BIND`, que se registra y
**no** desactiva el scope).

Webhooks con `signature_secret`: HMAC-SHA256 de `{timestamp}.{body}` en
`X-MetaTracer-Signature`. El API no vuelve a mostrar el secreto.

## Información y modelo opcional

El análisis almacena metadatos y hallazgos en la base de datos configurada. El modelo de lenguaje es opcional: cuando se habilita, recibe información derivada de los hallazgos, incluidos fragmentos de texto; los archivos completos no se envían al modelo. Revisa la configuración y las condiciones de privacidad del proveedor antes de activarlo.

Los informes pueden contener datos sensibles. La redacción de datos se aplica al archivo exportado: las opciones son `none`, `contacts`, `coordinates` y `all`. La API y la CLI utilizan `none` por defecto; la interfaz propone `contacts`. La redacción no modifica los datos guardados en la base de datos.

La lista de variables y sus valores de ejemplo está en [`.env.example`](../.env.example).
