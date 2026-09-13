# TASK-16: CI guardrail (v2.2)

**Módulo:** Integraciones — calidad automatizada como barrera de entrada
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Requisitos técnicos](../features/07-technical-requirements.md)
**Dependencias:** TASK-00 … TASK-15 (v1.0–v2.2 cerradas)
**Estado:** **Cerrada y validada 2026-09-13** — workflow `ci.yml` + scripts locales + umbral `fail_under=85` en `pyproject.toml`. Verificado localmente: `ci-check.ps1` exit 0, `pytest` completo **439 passed** (incluye e2e contra mock loopback), cobertura **90.63% ≥ 85%**, `ruff` limpio.

---

## 1. Objetivo técnico

Hasta ahora el DoD de cada task se verificaba **a mano** (`pytest` + `ruff`
local). Esta task lo convierte en un **guardrail automático** en GitHub
Actions, más un script local que replica la misma barrera sin depender de la
red. Un PR que no pase lint ni tests **no puede fusionarse**; el job full
verifica además el e2e contra el mock loopback y la cobertura.

La suite actual mide 439 tests; el e2e es **100% local** (uvicorn en
`127.0.0.1` efímero, sin red externa ni servicios), así que el job completo
puede correr sin secretos ni dependencias de terceros en CI.

## 2. Subtareas

### 16.1 Script local de guardrail

`scripts/ci-check.ps1` (Windows) y `scripts/ci-check.sh` (Unix): un único
comando que reproduce la barrera de PR localmente:

1. `python -m ruff check src tests` — cero findings.
2. `python -m pytest -m "not e2e" -q` — suite rápida (no requieren loopback).
3. Salida en texto plano de **qué ha pasado y qué ha fallado**, exit code no
   cero si algo falla (encadenable en CI y en pre-push local).

Sin lógica de secrets, sin cachés, sin red. No duplica la lógica de CI;
simplemente invoca las mismas herramientas con los mismos argumentos.

### 16.2 Workflow GitHub Actions `.github/workflows/ci.yml`

Dos jobs, ninguno usa servicios de contenedor ni secretos:

- **`pr`** (dispara en `pull_request`):
  - Checkout.
  - `actions/setup-python` con `python-version: 3.11` y caché de pip.
  - Instalar `.[dev]` (NO `pip install -e .`; instala desde `pyproject.toml`).
  - `ruff check src tests` y `pytest -m "not e2e" -q`.
- **`main`** (dispara en `push` a `master`; requiere el job `pr`):
  - Entorno completo (setup-python 3.11, dependencias desde `pyproject`).
  - `pytest -q` **incluyendo e2e** (loopback local, sin flag de entorno:
    el e2e escribe `Settings(allow_loopback=True)` en proceso, no requiere
    `METATRACER_ALLOW_LOOPBACK`).
  - **Cobertura**: `pytest --cov=metatracer.core --cov=metatracer.detectors
    --cov=metatracer.extractors --cov=metatracer.reports
    --cov-report=term-missing`, con umbral **≥ 85%** (DoD TASK-07, validado
    con 91% actual) vía `--cov-fail-under=85`.
  - `actions/upload-artifact` opcional: `.coverage` y reportes de la suite
    (para depurar o alimentar Codecov más adelante).

### 16.3 Umbral de cobertura

- **85% combinado** sobre los 4 paquetes, directamente desde `pyproject.toml`:
  `[tool.coverage] fail_under = 85` usando el `source` ya declarado
  (`src/metatracer`). Así el umbral es **un solo lugar de verdad** (TASK-07)
  y CI/local lo comparten.

### 16.4 Pin exacto de acciones

Todas las acciones con **SHA completo** (supply-chain, threat 15: nada de
tags flotantes que permitan a un tercero cambiar el código ejecutado):

- `actions/checkout` — SHA completo.
- `actions/setup-python` — SHA completo, cache `pip`.
- `actions/upload-artifact` — SHA completo, name/retention-days.

Los **workflows** van a la raíz de `.github/workflows/` (no a un subdir).

## 3. Fuera de alcance (de esta task)

- Matrix de versiones de Python en CI (el contrato refleja 3.11 local y 3.12
  en Docker; un matrix real queda como paso posterior).
- Codecov/coveralls u otro servicio externo de coverage.
- SonarQube, bandit u otros linters adicionales.
- CD: builds, push a registry, despliegues.
- Branches de protección / required checks (decision del propietario del repo,
  no configurable desde un workflow).

## 4. Tests mínimos

- El guardrail local y el workflow no pueden "testearse" con pytest; su prueba
  es ejecutarlos:
  - `scripts/ci-check.ps1` termina con exit code 0.
  - `ruff check src tests` limpio.
  - `pytest -m "not e2e"` verde.
  - `pytest --cov ... --cov-fail-under=85` verde.

## 5. Criterios de aceptación (DoD)

- [x] `scripts/ci-check.ps1` y `.sh` corren y devuelven 0 en un repo sano.
- [x] `ruff check src tests` limpio y `pytest -m "not e2e"` verde (verificado
      localmente antes del commit).
- [x] Cobertura combinada de los 4 paquetes ≥ 85% (validado con 91% actual)
      con `fail_under` en `pyproject.toml`.
- [x] `.github/workflows/ci.yml` con dos jobs (`pr` rápido, `main` completo
      con e2e + cobertura), acciones con SHA completo, sin secretos.
- [x] El job de main corre el e2e completo contra el mock loopback **sin
      depender de red externa ni de `METATRACER_ALLOW_LOOPBACK` en el entorno**
      (el flag se fija en proceso dentro de los tests).
- [x] README de tasks y timeline actualizados con TASK-16 cerrada.