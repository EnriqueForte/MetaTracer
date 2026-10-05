# TASK-07: Testing, Fixtures de Validación y Despliegue con Docker

**Módulo:** Calidad, Pruebas y Despliegue  
**Referencia PRD:** [Requisitos Técnicos](../features/07-technical-requirements.md), [Criterios de Éxito](../features/09-success-criteria.md), [Timeline](../features/10-timeline-and-roadmap.md)  
**Dependencias:** [TASK-00](00-architecture-and-safety.md) … [TASK-06](06-interfaces.md)  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Cerrar el MVP con: (1) fixtures sintéticos autorizados que cubren los 5 tipos, (2) suite pytest que incluye e2e del pipeline, (3) imagen Docker + Compose para local sin Python host.

Los tests unitarios de tasks anteriores **ya deben existir**. Esta task los completa, añade el factory, el servidor mock, e2e y el contenedor.

---

## 2. Subtareas Detalladas

### Subtarea 7.1: Fixtures sintéticos

Script `tests/fixtures/generate_test_fixtures.py` (o `python -m tests.fixtures.generate`):

| Fixture | Contenido | Tipo que debe disparar |
| :--- | :--- | :--- |
| 1 JPEG GPS | EXIF lat `40.4168`, lon `-3.7038` | `gps` |
| 2 PDF email | `/Author` y `/Creator` = `security.lead@acme-corp.internal` | `email` |
| 3 PDF path | XMP con `C:\Users\dev_admin\Projects\ConfidentialApp\build.pdf` | `internal_path` |
| 4 PDF software | `/Producer` = `Apache FOP Version 2.4` | `software_version` |
| 5 PDF/JPEG debug | `TODO: delete staging API key before public release - JIRA-4412` | `debug_comment` |
| 6 Limpio | PDF + JPEG sanitizados | **cero** findings |

Usar Pillow + piexif y reportlab/pypdf. Dominio sintético: `acme-corp.internal` (`.test` ya no es un buzón; TASK-34).

**Servidor mock:** `pytest` fixture HTTP (`httpx` ASGI o `uvicorn` en puerto efímero) que sirve esos archivos y una página HTML que los enlaza.

**Conflicto de safety (obligatorio de resolver):** `NetworkSafetyGuard` bloquea loopback. El e2e **debe** activar `METATRACER_ALLOW_LOOPBACK=true` **solo** en el proceso de test (monkeypatch de Settings / env). Añadir un test que demuestre: con el flag en `false`, el mock local es rechazado. El flag no se documenta como feature de usuario en el README de producto; sí en `tests/` y en `.env.example` como “test only”.

No usar sitios de terceros en CI.

---

### Subtarea 7.2: Suite pytest

Marcas: `unit`, `integration`, `e2e`, `slow`. Default: no correr `e2e` si se pide `-m "not e2e"` en CI rápido; CI completo corre todo.

Cobertura: **≥ 85% en `metatracer.core`, `metatracer.detectors`, `metatracer.extractors`, `metatracer.reports`**. El paquete `agents` cuenta menos (código con mocks). No perseguir 85% global inflando tests triviales de prompts.

#### 7.2.1. Unit (completar huecos)

Ya definidos en tasks 00–06. Verificar que existen y pasan.

#### 7.2.2. Agents

Mocks de LLM. Cero red real. Ver TASK-05.

#### 7.2.3. E2E `tests/integration/test_e2e_pipeline.py`

Flujo: mock origin in-scope (loopback + flag) → discover → extract → detect → classify (heurístico; agente mockeado o fallback) → report.

Criterios de éxito del PRD:

1. Al menos **4 de 5** tipos de finding sobre el set de fixtures (idealmente 5).
2. Markdown con evidence, impact, remediation.
3. Filas en SQLite para run, assets, findings.

También: documento limpio → 0 findings; redirect off-scope → no body.

---

### Subtarea 7.3: Docker

- **7.3.1. `Dockerfile` multi-stage:** `python:3.12-slim` o `3.11-slim` (alineado con `requires-python`). `libjpeg` + `zlib`. Usuario no-root `metatracer`. Entrypoint que acepte `web` (uvicorn) o pase args a la CLI.
- **7.3.2. `.dockerignore`:** `.venv`, `data/*.db`, `.git`, `.env`.
- **7.3.3. `docker-compose.yml`:**
  - Servicio web: puerto `8000`, `BIND_HOST=0.0.0.0`
  - Volúmenes: `./data:/app/data`, `./reports:/app/reports`
  - Env: `METATRACER_LLM_API_KEY`, `METATRACER_LLM_BASE_URL`, `METATRACER_LLM_MODEL`, `METATRACER_FAST_MODEL`, `LOG_LEVEL`
  - **No** definir `METATRACER_ALLOW_LOOPBACK=true` en Compose de producto.
- **7.3.4. CLI efímera:**

  ```bash
  docker run --rm -it \
    -v "$(pwd)/reports:/app/reports" \
    -e METATRACER_LLM_API_KEY \
    metatracer scan example.com -s example.com -y
  ```

  Script `scripts/docker-metatracer.ps1` (Windows) y opcional `.sh`. Documentar en el README raíz.

- **7.3.5.** Healthcheck HTTP `GET /` o `/api/health` simple (añadir endpoint `{ "status": "ok" }` si no existe).

CI con GitHub Actions es **opcional** en el MVP; si se añade, `ruff` + `pytest -m "not e2e"` en PR y e2e en main.

---

## 3. Fuera de alcance de esta tarea

- Kubernetes, registry público, firmado de imágenes.
- Fuzzing de parsers, tests contra programas de bounty reales sin scope.
- Cobertura 85% de prompts/LLM reales.

---

## 4. Criterios de Aceptación (DoD)

- [x] `pytest` de la suite acordada en verde. Cobertura ≥ 85% en módulos core/detectors/extractors/reports.
- [x] El factory genera archivos reales que disparan los 5 detectores + el caso limpio.
- [x] E2E usa loopback **solo** con el flag de test; sin flag, loopback sigue bloqueado.
- [x] Docker build OK; Compose sirve la UI en el puerto mapeado.
- [x] Scan en contenedor escribe el reporte en el volumen del host.
- [x] El e2e cubre los 3 criterios de éxito del PRD (tipos, reporte enviable, persistencia/arquitectura recorrida).
