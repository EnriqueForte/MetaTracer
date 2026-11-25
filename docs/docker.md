# Docker

[Volver al README](../README.md)

## Docker

Un origen (cookie `SameSite=Lax`, CSP `connect-src 'self'`):

| Servicio | Rol |
| --- | --- |
| `web` | FastAPI (API + SSE), no publicado al host |
| `web-v2` | Next.js, sin secretos ni base de datos |
| `proxy` | Caddy en el puerto 8000 |

```bash
docker compose up --build
```

UI en [http://localhost:8000](http://localhost:8000). Compose activa auth
porque publica un bind no-loopback. CLI efímera:

```bash
./scripts/docker-metatracer.sh scan example.com -s example.com -y
```

```powershell
.\scripts\docker-metatracer.ps1 scan example.com -s example.com -y
```

La imagen **no** define `METATRACER_ALLOW_LOOPBACK`.
