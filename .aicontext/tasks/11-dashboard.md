# TASK-11: Dashboard agregado (v2.0)

**Módulo:** Plataforma — dashboard  
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md)  
**Dependencias:** TASK-10 (scopes persistentes cerrado), TASK-00 … TASK-09  
**Estado:** En curso

---

## 1. Objetivo técnico

Segundo slice de **v2.0 Plataforma**: a vista de producto, el historial de runs
de v1.1 es una tabla plana. El dashboard agrega **todos** los runs y findings para
responder preguntas que el historial no puede:

- ¿Cuántos runs he hecho y cuál es el estado general (completados/fallidos)?
- ¿Cuántos findings se han encontrado en total, y cómo se distribuyen por
  severidad y tipo?
- ¿Qué **dominios** aparecen con más frecuencia en el scope confirmado?
- ¿Cuánto costó el análisis (agente LLM: llamadas, tokens, tiempo)?

Es **solo lectura** y **debe funcionar sin agentes**: el dashboard se construye
100% sobre columnas ya persistidas (`run`, `asset`, `finding`, `agent_log`).
Cero métricas dependientes de la ejecución en vivo. `agent_log` está poblado
solo cuando los agentes corrieron; si no, los contadores de agente son `0`.

Un solo endpoint, `GET /api/stats`, y una página `/dashboard` que lo consume.

---

## 2. Subtareas

### 11.1 Contratos (enums y reglas)

Cero valores nuevos: `severity`, `confidence`, `finding_type`, `run.status`,
`extraction_status`, `skip_reason`, `namespace`, `reasoning_depth`, `detector_method`
quedan igual. No se añade ningún enum.

Reglas de negocio del dashboard:

- Los **totales** cuentan solo `finding.severity` **no-NULL** (un finding sin
  clasificar sigue siendo contable en el total global, pero no en el desglose).
- `unclassified` es el bucket para `severity=None`, nunca un valor de enum.
- El desglose por severidad sigue el orden canónico del reporte:
  `critical → high → medium → low → info → unclassified`. El desglose por tipo
  sigue el orden canónico: `gps → email → internal_path → software_version →
  debug_comment`.
- `top_domains` se calcula sobre los **dominios normalizados** con
  `ScopeValidator.normalize_host` de `Run.allowed_scope` y `Asset.final_url`.
- El top de evidencia agrega por `dedup_signature`: el mismo snippet en muchos
  assets cuenta **una vez** (es la señal de “esto está por todo el target”).
- Límites de respuesta: `top_domains` y `top_evidence` a **10** entradas.
- `agent_usage` suma de `agent_log`: `calls`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `latency_ms` (total); si no hay filas, cero.

### 11.2 Repository analítico

Nuevo `DashboardRepository` (en `metatracer/db/repositories.py`, acepta una
`AsyncSession`):

- `summary()` → `(total_runs, by_status: Counter[str,int], total_assets,
  total_findings, by_severity: Counter[str,int], by_type: Counter[str,int],
  unclassified: int)`.
- `top_domains(limit=10)` → `list[tuple[str, int]]` sobre `Asset.final_url`
  normalizado **y** `Run.allowed_scope`.
- `top_evidence(limit=10)` → `list[tuple[str, int]]` agrupando por
  `dedup_signature` (con el primer snippet y el tipo como ejemplo).
- `agent_usage()` → `(calls, prompt_tokens, completion_tokens, total_tokens, latency_ms)`.

Sin JOINs complejos: leer `Run` + `Finding` + `Asset` + `AgentLog` de una vez
(volúmenes del MVP), normalizar y contar en Python. No hay lógica de negocio en
este layer: solo trae filas y agrega.

### 11.3 Service `DashboardStatsService` (código compartido)

Nuevo `services/dashboard.py` con:

```
DashboardStatsService(session_factory)
  async def build() -> DashboardStats
```

- `DashboardStats` (Pydantic): `runs` (total+por estado), `assets` (total y
  #con issues), `findings` (total + desglose severidad/tipo + unclassified),
  `top_domains`, `top_evidence`, `agent_usage`.
- `build()` abre **una** sesión, delega en `DashboardRepository` y compone el
  modelo; no consulta nada más.
- Solo lectura: **nunca** escribe.

### 11.4 API `GET /api/stats`

Nuevo router `api/stats.py` (prefix `/api/stats`, tag `stats`):

```text
GET /api/stats  -> 200 DashboardStats
```

- `DashboardStats` está en `api/schemas.py` (o en `api/stats.py`); los enums
  viajan en minúsculas (contrato), `unclassified` solo en `severity_breakdown`.
- 404 no aplica (siempre 200, incluso con 0 runs: el dashboard muestra vacío).
- Sin filtros por query param en este slice.

### 11.5 Web UI `/dashboard`

- Página `templates/dashboard.html` con Alpine.js: carga `GET /api/stats`,
  muestra fallo digno si no responde.
- Secciones:
  1. **KPI cards** — total runs, completados/fallidos, findings totales,
     "dominios únicos en scope" (len de `top_domains` agregado).
  2. **Severity breakdown** — barras horizontales (CSS, sin librerías; los
     % calculados en JS con `Math`).
  3. **Findings by type** — chips con conteo.
  4. **Top domains** — tabla (dominio, veces, link a los runs del dominio).
  5. **Top evidence** — snippet + nº de assets donde aparece.
  6. **Agent usage** — cards pequeñas (llamadas, tokens, latencia).
  - Cero `x-html`/`innerHTML`; todo por `x-text`/`textContent` y `:style`
    con **anchos calculados numéricamente** (nunca concatenar strings con CSS
    que venga de datos).
- Nav en `base.html`: enlace `Dashboard` junto a `New scan` / `History` / `Scopes`.
- Footer/header: mismo tono visual, sin dependencias nuevas.

### 11.6 Safety y persistencia

- **Solo lectura**: el endpoint no puede escribir ni borrar (nada de
  `session.commit()` en `Dashboard*`).
- **Cero secretos/bytes**: `AgentLog.raw_response` **no** viaja al dashboard
  (nunca se expone en la API); solo los contadores numéricos.
- **Cero red nueva**: no se abre ningún socket en `/api/stats`.
- Snippet de evidencia limitado a ~150 chars en la respuesta

---

## 3. Fuera de alcance

- Autenticación, multi-tenant, filtros por query param, paginación del top.
- Dashboard en tiempo real (SSE) o charts con librerías JS.
- Nuevos enums o columnas DB (no hay migración).
- Export/copy del dashboard, protector de gráficas tipo “business”.
- Notificaciones (siguiente slice v2.0); RAG/feedback (v2.1+).

---

## 4. Tests mínimos

- `tests/unit/test_dashboard_repository.py` — con filas sembradas (runs en
  varios estados, findings de varios tipos/severidades incl. `None`, assets con
  dominios, `agent_log`): `summary` cuenta bien, `top_domains` normaliza,
  `top_evidence` agrupa por `dedup_signature`, `agent_usage` suma.
- `tests/unit/test_dashboard_service.py` — `DashboardStatsService.build()` con
  cero filas (todo en cero, no excepciones) y con datos (totales y top correctos).
- `tests/integration/test_api_stats.py` — `GET /api/stats` 200 con 0 runs;
  200 con data; el payload cumple el contrato (keys, enums, `unclassified` en
  severidad); sin `raw_response` en la respuesta.
- `tests/integration/test_dashboard_page.py` — `/dashboard` 200 HTML con
  “Dashboard” (puede vivir dentro del test de stats).
- El resto de la suite sigue verde.

---

## 5. Criterios de aceptación (DoD)

- [ ] `GET /api/stats` devuelve KPIs, desgloses, top dominios, top evidencia y
      uso de agente sobre los datos persistidos.
- [ ] El dashboard funciona con **cero runs** (todo cero, página digna).
- [ ] El dashboard funciona **sin agentes** (agente `0`, no falla).
- [ ] `top_evidence` agrupa por `dedup_signature` (el mismo snippet en N assets
      cuenta una vez).
- [ ] `top_domains` normaliza (`Target.COM/path` → `target.com`).
- [ ] `AgentLog.raw_response` / bytes / secretos **nunca** aparecen en la respuesta.
- [ ] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio.
- [ ] Nada de esto escribe en la BD (los tests lo comprueban con `count()`).