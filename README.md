<div align="center">

<img src="web/src/app/icon.svg" alt="MetaTracer" width="72" height="72">

# MetaTracer

**Descubrimiento de metadata sensible en assets públicos, para bug bounty y red team autorizados.**

[Instalación](#instalación) · [Arranque](#arranque) · [Primer escaneo](#primer-escaneo) · [Sitio de prueba](#sitio-de-prueba) · [Qué detecta](#qué-detecta) · [Docker](#docker)

</div>

> **Solo uso autorizado.** MetaTracer rastrea metadata en targets que tienes
> permiso explícito de probar (programa de bug bounty in-scope, contrato de
> auditoría o tus propios assets). Cada run exige confirmar el alcance. No hay
> modo oculto ni inseguro en la distribución por defecto. El objetivo es
> **quitar** metadata sensible, no explotarla.

## Qué es

MetaTracer recorre páginas y ficheros **públicos** in-scope (PDF, imágenes,
HTML, JS, cabeceras HTTP, documentos de oficina) y extrae metadata: GPS,
correos, rutas internas, versiones, comentarios de debug, endpoints internos,
almacenamiento en la nube y secretos en valores ya extraídos.

La detección es **determinista**. Un LLM opcional solo interpreta hallazgos
ya vistos; un guard post-modelo no puede inventar evidencia ni subir
severidad sin texto que lo justifique. Los bytes de los ficheros **nunca** se
guardan ni se envían al modelo: solo metadata y snippets cortos.

Una instalación, dos superficies (mismos findings):

| Superficie | Dirección | Para qué |
| --- | --- | --- |
| **Web UI** (español) | [127.0.0.1:3000](http://127.0.0.1:3000) | Wizard de scan, historial, triage, grafos, informes |
| **API** | [127.0.0.1:8000](http://127.0.0.1:8000) | JSON + SSE; la CLI habla con el mismo orquestador |
| **CLI** (inglés) | terminal | `scan`, `watch`, `findings`, exports |

La UI es Next.js en `web/`. FastAPI es **solo API**. En local el lanzador
arranca las dos. En producción, Caddy sirve un solo origen (`/api` → FastAPI).

## Instalación

| Herramienta | Requisito |
| --- | --- |
| Git | Para clonar |
| Python | **3.11 o 3.12** (3.13 no está soportado) |
| Node.js | **20 o posterior**, con `npm` |
| Docker y Compose | Opcional; alternativa al instalador nativo |

```bash
git clone https://github.com/EnriqueForte/MetaTracer.git
cd MetaTracer
```

### Windows

Python 3.12 y Node LTS, si faltan:

```powershell
winget install Python.Python.3.12 OpenJS.NodeJS.LTS Git.Git
```

```powershell
.\install.cmd
.\MetaTracer.cmd
```

`install.cmd` y `MetaTracer.cmd` también se abren con doble clic.

### Linux (Debian / Parrot)

```bash
chmod +x install.sh run.sh    # o: bash install.sh
./install.sh
./run.sh
```

El instalador crea `.venv`, instala el paquete Python y la Web UI (`npm ci`),
y copia `.env.example` → `.env` si aún no existe. **Ctrl+C** detiene la app.

#### Parrot 7 (Python del sistema = 3.13)

Apt **no** ofrece `python3.11` ni `python3.11-venv`. Si ya tienes Python 3.11
en `~/.local` (o pyenv), crea el entorno con `virtualenv` y luego el
instalador:

```bash
sudo apt install python3-virtualenv python3-pip
rm -rf .venv
python3 -m virtualenv -p "$HOME/.local/bin/python3.11" .venv
./install.sh
```

Si `npm ci` corta con `ETIMEDOUT`, no borres `.venv`. Reintenta solo la UI:

```bash
cd web
export NODE_OPTIONS=--dns-result-order=ipv4first
npm ci
cd ..
./run.sh
```

### Extras de desarrollo

```bash
./install.sh --dev          # Linux
.\install.cmd --dev         # Windows
```

Instala `pytest` y `ruff` además del runtime.

## Arranque

Con el instalador ya ejecutado:

| Sistema | Comando | UI | API |
| --- | --- | --- | --- |
| Windows | `.\MetaTracer.cmd` | [127.0.0.1:3000](http://127.0.0.1:3000) | [127.0.0.1:8000](http://127.0.0.1:8000) |
| Linux / Parrot | `./run.sh` | igual | igual |

Mantén la terminal abierta. En una VM, abre esas URLs en el navegador de la VM.

Un overlay rojo de hidratación en Next.js con atributos `data-darkreader-*`
lo provoca **Dark Reader** (u otra extensión que reescribe el HTML). No es un
fallo de MetaTracer: desactívala en `127.0.0.1` o ignora el overlay. El tema
Sistema / Oscuro / Claro va en la propia UI.

## Primer escaneo

1. El lanzador abre [http://127.0.0.1:3000/login](http://127.0.0.1:3000/login).
   Si la base está vacía, usa **Crear la primera cuenta** (`/setup`) y pega el
   token `SETUP MODE` que sale **una vez** en la terminal.
2. Crea un scan, indica el host **y el scope**. El scope no se infiere.
3. Confirma que estás autorizado. Sin esa confirmación no hay HTTP.
4. Revisa hallazgos, triaje (`open` / `confirmed` / `false_positive` / `fixed`)
   y exporta el informe (Markdown, JSON, HTML, CSV o plantilla bounty, **en inglés**).

Loopback y redes privadas están bloqueados. No uses la app contra `localhost`
salvo la suite de tests. Un overlay de extensión no impide escanear.

CLI equivalente (Linux):

```bash
.venv/bin/python -m metatracer scan example.com -s example.com -y
```

Windows: `.venv\Scripts\python.exe` en lugar de `.venv/bin/python`. `-y`
confirma el alcance sin pregunta interactiva.

Para un primer recorrido sin un programa de bug bounty, usa el [sitio de prueba](#sitio-de-prueba).

## Sitio de prueba

[Puertomontevideo](https://puertomontevideo-lab.serious-radius.workers.dev) es un semanario portuario **ficticio** publicado por este proyecto. Sirve para ejercitar el crawl en HTTPS: loopback sigue bloqueado, así que `localhost` no vale.

| Campo | Valor |
| --- | --- |
| Objetivo | `https://puertomontevideo-lab.serious-radius.workers.dev` |
| Scope | `puertomontevideo-lab.serious-radius.workers.dev` |

El scope es el host entero. `workers.dev` a secas queda fuera de alcance.

```bash
.venv/bin/python -m metatracer scan https://puertomontevideo-lab.serious-radius.workers.dev -s puertomontevideo-lab.serious-radius.workers.dev -y
```

Qué hay plantado (fotos, actas, metadata) está en [`lab/puertomontevideo/README.md`](lab/puertomontevideo/README.md). No es un medio real ni un target de terceros.

## Qué detecta

| Tipo | Ejemplos |
| --- | --- |
| `gps` | Coordenadas EXIF / IPTC |
| `email` | Correos en metadata y comentarios |
| `internal_path` | Rutas de disco o UNC |
| `software_version` | Producto y versión en PDF / cabeceras |
| `debug_comment` | Comentarios HTML/JS de desarrollo |
| `internal_endpoint` | Hosts `.internal` / RFC1918 en metadata |
| `cloud_storage` | Hosts S3, GCS, Azure Blob, R2 |
| `secret` | Allowlist: `AKIA`, `ghp_`, PEM, JWT compacto **ya extraídos** |

Fuentes: JPEG/PNG/TIFF/WebP/GIF, SVG (solo RDF/metadata, nunca el dibujo),
PDF, HTML, cabeceras HTTP, comentarios JS, propiedades OOXML/ODF (nunca el
cuerpo). También una **carpeta local** (`--local` / `local_paths`): mismos
extractores, cero red. No se descomprimen ZIP genéricos ni se piden HEIC/AVIF.

## Cómo trabaja el pipeline

1. **Safety** — scope confirmado, un único wrapper HTTP, redirects revalidados,
   proxies de entorno ignorados (`trust_env=False`).
2. **Ingesta** — crawl de profundidad 1, allowlist por magic bytes.
3. **Detectores** — reglas; la severidad queda vacía.
4. **Clasificador heurístico** — rúbrica con techos por tipo (siempre disponible).
5. **Agente** (opcional) — un hallazgo por llamada; si el modelo falla, queda
   la heurística.
6. **Informe y triaje** — el operador marca falsos positivos; no se reescribe
   la evidencia.

El LLM es opcional (`METATRACER_LLM_*` en `.env`). Sin clave, solo corre la
heurística.

## CLI útil

```bash
.venv/bin/python -m metatracer scan example.com -s example.com -y
.venv/bin/python -m metatracer watch <scope-id> --once
.venv/bin/python -m metatracer watch <scope-id> --interval 21600 --webhook <webhook-id>
.venv/bin/python -m metatracer findings triage <finding-id> --status false_positive
```

`watch` reescanea un scope guardado y reporta deltas (`new_findings`,
`resolved_findings`, `severity_up_count`) **sin** mandar evidencia al webhook.

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

## Verificar (contribuidores)

```bash
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m pytest -m "not e2e"
```

Windows: `.venv\Scripts\python.exe`. Cobertura DoD ≥ 85 % en
`core` / `detectors` / `extractors` / `reports`.

## Documentación interna

El estado vigente está en [`MEMORY.md`](MEMORY.md). El resto cuelga de ahí:

| Documento | Qué es |
| --- | --- |
| [`specs/current.md`](specs/current.md) | Qué hace el producto ahora |
| [`specs/README.md`](specs/README.md) | Ritual SDD y mapa de specs |
| [`specs/backlog.md`](specs/backlog.md) | Specs 00 y 36–56, con estado |
| [`.aicontext/tasks/README.md`](.aicontext/tasks/README.md) | Contratos, enums y tasks |
| [`.aicontext/PRD.md`](.aicontext/PRD.md) | Índice histórico del PRD (hasta v3.2) |
| [`.aicontext/ui/design-system-v2.md`](.aicontext/ui/design-system-v2.md) | Contrato visual de la Web UI |
| [`AGENTS.md`](AGENTS.md) | Punto de entrada para agentes |
| [`tests/README.md`](tests/README.md) | Marcas, loopback de test y cobertura |
| [`lab/puertomontevideo/README.md`](lab/puertomontevideo/README.md) | Target sintético (spec 53; host público en spec 54) |
| [`.aicontext/walkthrough.md`](.aicontext/walkthrough.md) | Recorrido de arquitectura hasta v3.2 |

El walkthrough no sustituye a `MEMORY.md`: los tipos de hallazgo vigentes y las specs 36–56 están en la memoria y en `specs/`.

**Tecnologías:** Python · FastAPI · Next.js · React · TypeScript · LangGraph · SQLite / PostgreSQL.

## Autor

**Enrique Forte · T3r0S3c** · [GitHub](https://github.com/EnriqueForte) ·
[LinkedIn](https://linkedin.com/in/enriqueforte)

Uso autorizado en programas de bug bounty, auditorías y assets propios.
No es un framework de explotación.
