---
name: metatracer-testing
description: Convenciones de test de MetaTracer (marcas por directorio, DNS y transporte fakeados sin mockear el safety, mock origin loopback, flag METATRACER_ALLOW_LOOPBACK solo-test, fixtures sintéticos, umbral de cobertura 85% y Docker multi-stage). Usar al escribir tests, fixtures, tests de seguridad negativos, e2e, o al tocar Dockerfile/docker-compose/CI.
---

# Testing y despliegue

Fuente: `.aicontext/tasks/07-testing-and-deployment.md`, `tests/README.md`.

## Regla de oro

**Nunca se mockea un control de safety para que un test pase.** Se fakean
DNS y transporte; `ScopeValidator` y `NetworkSafetyGuard` se ejecutan **reales**
(`tests/conftest.py`). Si el guard estorba, el test está mal planteado.

## Marcas (`pyproject.toml` + `conftest.py`)

| Directorio | Marca | Contenido |
| :--- | :--- | :--- |
| `tests/unit/` | `unit` | Rápido, un módulo. |
| `tests/agents/` | `unit` | Agente con **LLM fake**; cero red real. |
| `tests/integration/` | `integration` | Multi-módulo; transporte fake o mock origin. |
| `test_e2e_pipeline.py` | `integration` + `e2e` | Pipeline completo sobre HTTP loopback real. |

Las marcas por directorio se aplican automáticamente
(`pytest_collection_modifyitems`); `e2e` vive en el propio módulo. `slow` está
registrada para uso futuro.

- Loop rápido (CI PR): `pytest -m "not e2e"`
- Suite completa (CI main): `pytest`

## Loopback y `METATRACER_ALLOW_LOOPBACK` — **solo tests**

El e2e escanea un mock origin real (`uvicorn` en `127.0.0.1`, puerto efímero,
`tests/fixtures/mock_origin.py`). El guard bloquea loopback, así que el e2e
construye `Settings(allow_loopback=True)` (equivalente en proceso a la env var).

- El flag es **solo test**: nunca en el producto, la imagen, Compose ni la doc
  de usuario.
- Fuera de pytest, `enforce_loopback_test_only` **rechaza arrancar**
  (`PYTEST_CURRENT_TEST` es el marcador).
- Un test demuestra el default: sin el flag, el mock origin se rechaza
  **antes** de abrir socket.

## Fixtures sintéticos

- `tests/fixtures/generate_test_fixtures.py` (Pillow / pypdf / reportlab /
  piexif) construye los casos: JPEG con GPS, PDF con email, PDF con path, PDF
  con versión de software, PDF/JPEG con debug, y limpio.
- Dominio sintético **`acme-corp.internal`** (`.test` no es un buzón real).
- **Cero sitios de terceros**: el objetivo es el transporte fake
  (`httpx.MockTransport`) o el mock origin local.

## Cobertura (DoD)

Umbral **85%** sobre `metatracer.core`, `metatracer.detectors`,
`metatracer.extractors` y `metatracer.reports` (`fail_under = 85` en
`pyproject.toml`, compartido por CI y local). Medido: **91.30%**.

El paquete `agents` queda **fuera** del gate a propósito (código con LLM
mockeado); no inflar el número con tests triviales de prompts.

## CI (`.github/workflows/ci.yml`)

- `pr`: `ruff` + `pytest -m "not e2e"`.
- `main`: suite completa + cobertura ≥85% + artefacto.
- `web`: Vitest + `next build` + Playwright (`wizard.spec.ts`).
- `web-auth`: `playwright.auth.config.ts` (API con auth ON real).
- Acciones fijadas por **SHA completo** (cadena de suministro, amenaza 15).

## Docker (TASK-07)

Multi-stage sobre `python:3.12-slim`: builder instala desde `requirements.lock`
con `--require-hashes`; runtime **sin compiladores** (solo `libjpeg`, `zlib`),
usuario **no-root**, volúmenes solo `data/` y `reports/`, healthcheck
`GET /api/health`, `ALLOW_LOOPBACK` **nunca** presente.

## Tests de seguridad que deben existir

`test_network_safety_guard`, `test_safe_http`, `test_http_redirect_scope`
(redirect fuera de scope), `test_task27_security_hardening`,
`test_task29_output_integrity`, `test_feedback_classifier_injection`
(prompt injection), `test_api_auth` (401/403/CSRF/roles).

## Checklist

- [ ] Sin `pytest.mark.skip` ni `# noqa` para tapar un fallo.
- [ ] Ningún mock de `ScopeValidator` / `NetworkSafetyGuard`.
- [ ] Cero red de terceros; fixtures o mock origin.
- [ ] Test negativo por cada control de seguridad que se toca.
- [ ] Cobertura ≥85% en los 4 paquetes del gate.
- [ ] `ALLOW_LOOPBACK` solo en el proceso de test.
