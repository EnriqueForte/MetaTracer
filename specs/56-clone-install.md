# Spec 56 — Clone, instalador y lanzador (Windows + Linux/Parrot)

**Estado:** closed (2026-11-19)  
**Agente previsto:** `pipeline-engineer` (scripts) · `test-engineer` (DoD) · `docs-architect` (README/MEMORY)  
**Skill al abrir:** `metatracer-sdd` + `metatracer-supply-chain` + `metatracer-testing`  
**Task:** [.aicontext/tasks/56-clone-install.md](../.aicontext/tasks/56-clone-install.md)

## Intención

Tras `git clone`, un operador en **Windows** o en **Linux** (Debian/Parrot) ejecuta
**un instalador** y después **un lanzador de la app**. No tiene que memorizar venv,
`pip` ni `npm`. El stack local (FastAPI en `:8000` + Web V2 en `:3000`) arranca
igual que `npm run dev` en `web/`.

## Alcance

- Motor stdlib `scripts/desktop.py` (sin dependencias nuevas, sin importar
  `metatracer` — corre **antes** de `pip install`).
- Instalador de raíz: `install.cmd` (Windows, doble clic) y `install.sh`
  (Linux/Parrot).
- Lanzador de raíz: `MetaTracer.cmd` (Windows, doble clic) y `run.sh` (Linux).
- Prerrequisitos comprobados: Python **3.11 o 3.12**, Node.js **≥ 20**, `npm`.
  Si faltan, el instalador imprime el comando `winget` / `apt` y sale ≠ 0.
- Instalación: `.venv`, `pip install -e .`, `npm ci` en `web/`, copia de
  `.env.example` → `.env` solo si no existe, `data/` y `reports/`.
- El lanzador reutiliza `web/scripts/dev-with-api.mjs` (API + Next). Bind
  loopback por defecto. Nunca exporta `METATRACER_ALLOW_LOOPBACK`.
- README bilingüe de arranque (inglés, capa README/CLI).

## Fuera de alcance

PyInstaller, NSIS/MSI, `.deb`, Electron/Tauri, empaquetar Python/Node dentro
del repo, macOS como target declarado, auto-`sudo apt` / `winget install`,
Docker (sigue en `docker compose`), cambiar safety, enums o `src/`/`web/` de
producto. `--insecure` y flags ocultos siguen prohibidos.

## Dependencias

Web V2 `npm run dev` (TASK-35 / T11). Python `>=3.11,<3.13`. Node 20+ (Next 16).
