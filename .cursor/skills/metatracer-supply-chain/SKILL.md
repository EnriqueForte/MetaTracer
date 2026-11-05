---
name: metatracer-supply-chain
description: Gobierna la cadena de suministro de MetaTracer — lista cerrada de dependencias de TASK-00, separación runtime/dev, superficie de la imagen Docker, manejo de secretos y assets de terceros por CDN. Usar al tocar pyproject.toml, Dockerfile, docker-compose.yml, .dockerignore o .env.example, y antes de añadir cualquier import de un paquete de terceros.
---

# Cadena de suministro de MetaTracer

Cubre la amenaza 15 del modelo de amenazas. Referencia completa:
`.aicontext/tasks/00-architecture-and-safety.md` (0.1.3) y `07-testing-and-deployment.md` (7.3).

**Principio:** la lista de dependencias es **cerrada**. MetaTracer es una herramienta de
seguridad que un hunter ejecuta contra targets de terceros; cada paquete que entra ejecuta
código en su máquina. Añadir uno no es una decisión técnica menor, es ampliar el perímetro.

Si necesitas algo que no está en la lista: **para y pide aprobación**. No lo añadas "de paso".

## Lista aprobada (TASK-00, 0.1.3)

Runtime: `pydantic>=2.7`, `pydantic-settings>=2.3`, `sqlmodel>=0.0.18`, `aiosqlite>=0.20`,
`langgraph>=0.1.0`, `langchain-core>=0.2.0`, `langchain-openai>=1.0`,
`httpx>=0.27.0,<1`, `langsmith>=0.3.45,<0.12`, `openai>=1.0,<3`,
`pillow>=10.3.0`, `pypdf>=4.2.0`,
`typer>=0.12.0`, `rich>=13.7.0`, `fastapi>=0.111.0`, `uvicorn>=0.30.0`,
`jinja2>=3.1`, `beautifulsoup4>=4.12`, `tenacity>=8.3`, `python-dotenv>=1.0`.

Dev: `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=5.0`, `ruff>=0.4.0`,
`reportlab>=4.2`, `piexif>=1.1.3` (fixtures JPEG only; not imported from `src/`).

Optional extra `[onnx]` (TASK-40): `onnxruntime>=1.17.0,<2`, `tokenizers>=0.20.0,<1`.
Not in the default image. Local model file only; no runtime download.

Runtime: `requires-python = ">=3.11,<3.13"`, `ruff.target-version = "py311"`.

**Separación runtime/dev, no decorativa.** `reportlab` existe solo para generar fixtures de PDF
en TASK-07: un `import reportlab` desde `src/metatracer/` es un error, porque convertiría una
dependencia de test en dependencia de producto. Lo mismo con `pytest` y `ruff`.

## Antes de añadir una dependencia

1. ¿Lo resuelve la **stdlib**? (`hashlib`, `ipaddress`, `pathlib`, `urllib.parse`, `re`,
   `logging`, `mimetypes` cubren mucho de lo que este proyecto necesita).
2. ¿Lo cubre ya un paquete de la lista? No añadas un cliente HTTP nuevo teniendo `httpx`, ni
   otro parser de HTML teniendo `beautifulsoup4`.
3. **Nombre exacto** del paquete en PyPI, verificado carácter a carácter. El typosquatting vive
   de `pillow`/`pillow-simd`, `piexif`/`pyexif`, `beautifulsoup4`/`beautifulsoup`.
4. ¿Está mantenido y tiene releases recientes? ¿Licencia compatible?
5. ¿Ejecuta código en **import time**, abre red o lanza subprocesos? Para un parser de metadata
   eso es una señal de alarma.
6. ¿Arrastra extensiones nativas que obliguen a meter compiladores en la imagen Docker?
7. ¿Es **runtime** o basta como **dev**? Colócala donde toca.
8. Si entra: añádela a `pyproject.toml` **y** a la lista de TASK-00 en el mismo cambio, con una
   línea de por qué. Si la lista y `pyproject.toml` divergen, el proyecto ya no tiene lista
   cerrada.

## Prohibiciones

- Instalar paquetes en runtime: nada de `pip install`, `subprocess` a un gestor de paquetes, ni
  descarga y ejecución de código en caliente.
- `curl ... | sh` o binarios descargados sin verificar en el `Dockerfile`.
- Cargar plugins o entry points de terceros en tiempo de ejecución.
- Añadir una dependencia por comodidad de formato o de estilo (eso lo cubre `ruff`).
- Fijar una versión **máxima** de una dependencia de seguridad para esquivar un fallo: se
  arregla el código.

## Superficie de la imagen (TASK-07, 7.3)

- Multi-stage sobre `python:3.12-slim` o `3.11-slim`, alineado con `requires-python`. El stage
  final **no** conserva compiladores ni cabeceras de desarrollo.
- Solo las librerías de sistema necesarias: `libjpeg` y `zlib`.
- Usuario **no-root** `metatracer`.
- `.dockerignore` con `.venv`, `data/*.db`, `.git`, `.env`: la imagen no debe llevarse dentro
  secretos, la base de datos local ni el historial del repo.
- Volúmenes solo para `./data` y `./reports`. Nunca montar el código ni el home del host.
- Compose **sin** `METATRACER_ALLOW_LOOPBACK`. El flag es de tests, no de despliegue.
- Healthcheck simple (`GET /api/health`), no un endpoint que revele configuración.

## Secretos

- `.env` va en `.gitignore` y nunca entra en la imagen. Las claves se inyectan por variable de
  entorno en runtime.
- `.env.example` documenta nombres de variables, **jamás** valores reales.
- `METATRACER_ALLOW_LOOPBACK` puede aparecer en `.env.example` marcado como "test only".
- Ninguna clave se loguea ni se persiste en `AgentLog`.

## Assets de terceros de la UI (TASK-06; sin CDN desde TASK-26)

La Web UI cargaba Tailwind y Alpine.js desde CDN — cadena de suministro ejecutándose en el
navegador del hunter. **Cerrado con la opción A de TASK-26** (2026-09-21):

- Tailwind CSS 3.4.16 se compiló offline a `static/tailwind.css` con el CLI oficial
  (`tailwindcss-windows-x64.exe`, hash en TASK-26) y Alpine se sirve como build CSP 3.17.4
  vendorizado (`static/alpine-csp-3.17.4.min.js`) — sin `unsafe-eval`, sin orígenes de
  terceros.
- El binario compilador no se versiona, no entra en la imagen Docker y la app no lo descarga en
  runtime.
- Regla vigente: **no re-introducir ningún `<script src>` de terceros**, ni `@latest`, ni
  fuentes/iconos remotos. Las versiones de los assets servidos desde `static/` quedan fijadas
  por su contenido y su hash documentado.

Si algún día se añadiera un asset remoto (no previsto), aplicaría el régimen anterior: versión
exacta, dominio oficial, solo `https`, y revisión de `safety-guardian` (amenaza 15).

## Huecos conocidos de la lista

- **`langchain-openai` no está en la lista de TASK-00**, pero TASK-05 (5.2.2) pide un cliente
  `ChatOpenAI` apuntando a `LLM_BASE_URL`, y esa clase no vive en `langchain-core`. Antes de
  implementar TASK-05 hay que aprobar la dependencia y añadirla a TASK-00, o resolver el cliente
  con `httpx` contra la API compatible con OpenAI. No lo decidas dentro del código.

## Checklist de revisión

- [ ] Toda dependencia de `pyproject.toml` está en la lista de TASK-00 (y al revés).
- [ ] Ninguna dependencia de dev se importa desde `src/`.
- [ ] Sin instalación ni descarga de código en runtime.
- [ ] `.dockerignore` excluye `.env`, `.git`, `data/*.db` y `.venv`.
- [ ] Imagen final sin compiladores y con usuario no-root.
- [ ] Compose sin `ALLOW_LOOPBACK`; sin secretos en valores por defecto.
- [ ] URLs de CDN con versión fija y solo dominios oficiales.
