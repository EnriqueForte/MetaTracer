# TASK-34: Precisión de detectores y coste del agente (v3.2)

**Módulo:** `detectors/{email,gps,paths}.py`, `classification/{classifier,rubric}.py`, `agents/{pipeline,optimizer,llm}.py`, `core/config.py`
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P2 (precisión de detección)
**Dependencias:** TASK-29
**Estado:** **Pendiente** (planificada 2026-10-03).

---

## 1. Objetivo técnico

Reducir falsos positivos y falsos negativos reproducibles sin añadir valores a los enums cerrados, y desacoplar el presupuesto del agente del de assets. No se añade ningún `finding_type` (el tipo `secret` queda en el backlog y exige actualizar antes los contratos de `README.md`).

## 2. Subtareas

### 34.1 Email

- Rechazar candidatos cuyo "TLD" sea una extensión de archivo (`png`, `jpg`, `jpeg`, `gif`, `webp`, `svg`, `ico`, `css`, `js`, `pdf`…) y patrones retina `@\d+x\.`.
- Ampliar placeholders: `example.net`, `test.com`, `email.com`, `domain.com`, TLDs reservados `.test`, `.invalid`, `.example`, `.localhost`.

### 34.2 GPS

- Excluir coordenadas con `abs(lat) < 1e-5 and abs(lon) < 1e-5` (no solo `(0, 0)` exacto). Alinear con `parse_gps_line` en `classification/anchor.py`.
- Rúbrica: eliminar el nivel `critical` de GPS del prompt y de `rubric.py` (inalcanzable: el snippet nunca lleva contexto), o documentar por qué se mantiene. El techo heurístico sigue en `high`.

### 34.3 Marcador de secreto

- `classifier.py`: `critical` solo si hay valor asociado (`password\s*[:=]\s*\S`, `api[_-]?key\s*[:=]`, `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`, `-----BEGIN [A-Z ]*PRIVATE KEY-----`). La palabra sola (`"remove staging credentials"`) → `medium`.
- Actualizar `test_risk_classifier.py` (el caso actual que espera `critical`).

### 34.4 Rutas internas

- Añadir con confianza `medium`: `/private/tmp/`, `/private/var/`, `C:\Program Files`, `C:\ProgramData`, `AppData` fuera de `Users`, `~usuario/`.
- Documentar en el docstring por qué `/opt` y `/usr` siguen fuera.

### 34.5 Presupuesto y coste del agente

- Nuevo setting `METATRACER_MAX_AGENT_FINDINGS` (default 50) usado por `ContextOptimizer` en lugar de `max_assets_per_run`.
- Caché en memoria por run de respuestas del LLM indexada por hash del payload (findings idénticos en assets distintos).
- Concurrencia acotada opcional (`METATRACER_LLM_CONCURRENCY`, default 1) respetando `rate_limit_rps`.

## 3. Fuera de alcance

- Nuevos tipos de finding (`secret`, IPs privadas, autor, buckets).
- Geocoding o enriquecimiento externo (prohibido por las reglas).

## 4. Tests mínimos

- `image@2x.png`, `logo@3x.jpg`, `foo@example.net`, `a@b.test` → sin finding; `john@acme.com` → finding.
- GPS `0/1, 0/1, 1/1000` → sin finding; coordenadas reales → finding.
- `"remove staging credentials"` → `medium`; `password=hunter2` y `AKIAIOSFODNN7EXAMPLE` → `critical`.
- Cada ruta nueva detectada con confianza `medium`; `/usr/lib` sigue sin detectarse.
- Run con 120 findings y `MAX_AGENT_FINDINGS=100` → 100 agentizados; payloads repetidos → una llamada al LLM.

## 5. Criterios de aceptación (DoD)

- [ ] Falsos positivos de la auditoría eliminados con tests de regresión.
- [ ] Enums cerrados intactos.
- [ ] Presupuesto del agente configurable e independiente de `max_assets_per_run`.
- [ ] Suite verde + ruff limpio + cobertura ≥85%.
