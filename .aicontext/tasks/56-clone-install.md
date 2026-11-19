# TASK-56: Clone, instalador y lanzador (Windows + Linux/Parrot)

**Módulo:** `scripts/desktop.py`, wrappers de raíz  
**Spec:** [specs/56-clone-install.md](../../specs/56-clone-install.md)  
**Dependencias:** TASK-07 (venv/Docker), T11 (`web/` + `dev-with-api.mjs`)  
**Agentes:** `pipeline-engineer`, `test-engineer`; veto `safety-guardian` si se toca env de red  
**Estado:** **Cerrada 2026-11-19.** Stdlib only; wrappers en la raíz; 14 tests unitarios.

## 1. Objetivo técnico

Un clone fresco se instala con un ejecutable y se arranca con otro, en Windows
y en Linux/Parrot, sin dependencias nuevas y sin relajar safety.

## 2. Subtareas

- `scripts/desktop.py` (stdlib): `install` / `run`. Rechaza Python fuera de
  3.11–3.12 y Node &lt; 20. Crea venv, `pip install -e .` (`--dev` → `.[dev]`),
  `npm ci` en `web/`, `.env` desde ejemplo si falta, `data/` + `reports/`.
- `child_env()` copia el entorno y **elimina** `METATRACER_ALLOW_LOOPBACK`.
- Wrappers: `install.cmd`, `MetaTracer.cmd`, `install.sh`, `run.sh`.
  `.gitattributes`: `*.sh` LF, `*.cmd` CRLF. Bit ejecutable en los `.sh`.
- Lanzador: `METATRACER_PYTHON` = intérprete del venv; `npm run dev` en `web/`;
  espera `:3000`; abre el navegador salvo `--no-browser`.
- En POSIX, al instalar, `chmod +x` de `install.sh`/`run.sh` y un
  `MetaTracer.desktop` con `Exec` absoluto y `Terminal=true`.
- README: clone → instalador → lanzador. El flujo manual PowerShell queda como
  alternativa de contribuidor.

## 3. Safety / supply chain

- Cero paquetes nuevos. Cero binarios descargados. Cero `curl | sh`.
- No se escribe `METATRACER_ALLOW_LOOPBACK` en `.env` ni en el entorno hijo.
- No hay `--insecure`. Bind sigue siendo el de `metatracer serve` (loopback).
- El instalador no llama a `sudo`/`winget install`; solo imprime la receta.

## 4. Fuera de alcance

PyInstaller, MSI/NSIS, `.deb`, Electron, macOS declarado, auto-instalación de
sistema, cambios en `src/` o `web/` de producto.

## 5. Tests mínimos

- Versión Python: 3.10/3.13 rechazadas; 3.11 y 3.12 aceptadas.
- Node: `v18` rechazado; `v20`/`v24` aceptados.
- `child_env` no contiene `METATRACER_ALLOW_LOOPBACK` aunque el padre la tenga.
- `ensure_env_file` copia y no pisa un `.env` existente.
- `run` falla si falta `.venv` o `web/node_modules` (sin spawnear npm).
- `install` (con `run_command` / `venv.create` mockeados) invoca `pip install -e .`
  y `npm ci`; `--dev` usa `.[dev]`.
- Wrappers existen; `install.sh`/`run.sh` empiezan por shebang LF.

## 6. DoD

- [x] Spec 56 active → código → tests de la slice verdes
- [x] `ruff check src tests scripts` limpio
- [x] README documenta Windows y Linux/Parrot
- [x] Diff sin PyInstaller/Electron ni deps nuevas
