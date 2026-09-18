# TASK-00: Arquitectura Base, Persistencia y Núcleo de Safety

**Módulo:** Fundamentos y Seguridad  
**Referencia PRD:** [Requisitos Técnicos](../features/07-technical-requirements.md) y [Ética, Legal y Safety](../features/08-ethics-legal-safety.md)  
**Dependencias:** Ninguna  
**Estado:** Completada  

---

## 1. Objetivo Técnico

Establecer el esqueleto Python del proyecto, la configuración por entorno, el logging, la jerarquía de excepciones, la persistencia SQLite (SQLModel) y el Safety Core que actúa de gatekeeper de **todas** las operaciones de red.

Al cerrar esta task el repo debe ser instalable (`pip install -e .`) y el safety debe poder testearse **sin** extractores ni UI.

---

## 2. Subtareas Detalladas

### Subtarea 0.1: Estructura del Repositorio y Configuración del Proyecto

- **0.1.1. Layout del proyecto (estado final v2.3, 2026-09-16):**

  ```text
  metatracer/
    ├── src/
    │   └── metatracer/
    │       ├── __init__.py
    │       ├── __main__.py        # entry point Python -m metatracer
    │       ├── core/              # config, logging, safety/, ratelimit (v2.3)
    │       │   └── safety/        # scope, guard, http (gateway único de red)
    │       ├── db/                # engine, modelos, repositorios
    │       ├── extractors/        # ingesta, crawler, PDF/EXIF/HTML/JS/HTTP
    │       ├── detectors/         # 5 detectores + pipeline + consolidación
    │       ├── classification/    # rúbrica + clasificador heurístico (TASK-03)
    │       ├── agents/            # LangGraph, prompts versionados, guard (TASK-05)
    │       ├── reports/           # builders + exportadores md/json/html/csv/bounty
    │       ├── services/          # orchestrator, progress, notifications, dashboard
    │       ├── scopes/            # scopes persistentes + formato portable (TASK-10/19)
    │       ├── knowledge/         # RAG ligero FTS5 + KB portable (TASK-14/17)
    │       ├── cli/               # Typer + Rich (TASK-06)
    │       └── api/               # FastAPI: routers + templates/ + static/ (TASK-06)
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   ├── agents/
    │   └── fixtures/
    ├── data/                  # SQLite en runtime; gitignore del .db
    ├── reports/               # exportaciones; gitignore del contenido
    ├── .aicontext/            # PRD, features, tasks, ADRs, validación
    ├── .cursor/               # reglas, skills y agentes del ecosistema Cursor
    ├── scripts/               # check local de CI (ci-check.sh)
    ├── docker/                # entrypoint de la imagen
    ├── .github/workflows/     # CI guardrail (TASK-16)
    ├── Dockerfile, docker-compose.yml
    ├── pyproject.toml
    ├── .env.example
    ├── .gitignore
    └── README.md
  ```

- **0.1.2. Runtime:** Python **>=3.11,<3.13**. `requires-python` y `ruff.target-version = "py311"`.
- **0.1.3. Dependencias (`pyproject.toml`):**
  - Runtime: `pydantic>=2.7`, `pydantic-settings>=2.3`, `sqlmodel>=0.0.18`, `aiosqlite>=0.20`, `langgraph>=0.1.0`, `langchain-core>=0.2.0`, `langchain-openai>=1.0`, `httpx>=0.27.0`, `pillow>=10.3.0`, `pypdf>=4.2.0`, `piexif>=1.1.3`, `typer>=0.12.0`, `rich>=13.7.0`, `fastapi>=0.111.0`, `uvicorn>=0.30.0`, `jinja2>=3.1`, `beautifulsoup4>=4.12`, `tenacity>=8.3`, `python-dotenv>=1.0`.
  - Adición aprobada (TASK-05): `langchain-openai>=1.0` — cliente `ChatOpenAI` para la API compatible con OpenAI (Kimi/Moonshot vía `LLM_BASE_URL`); la clase no vive en `langchain-core`. Aprobada explícitamente al ejecutar TASK-05.
  - Adiciones aprobadas (TASK-23, 2026-09-17): `asyncpg>=0.29.0` — driver async de PostgreSQL (Eje B, único driver soportado, se exige en `create_db_engine`); `alembic>=1.13.0` — migraciones de esquema empaquetadas y ejecutadas programáticamente en `init_db` para el backend Postgres; `pgvector>=0.3.0` — plumbing pgvector para el índice vectorial del conocimiento (`PgVectorKnowledgeIndex`).
  - Dev: `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=5.0`, `ruff>=0.4.0`, `reportlab>=4.2` (fixtures de PDF en TASK-07; se puede declarar ya en dev).
  - Entry point: `[project.scripts] metatracer = "metatracer.cli.main:app"` (el módulo CLI puede ser un stub que imprima “not implemented” hasta TASK-06).
- **0.1.4. Ruff:** reglas `E`, `F`, `B`, `I`, `UP`. Line length 100.
- **0.1.5. `.gitignore`:** `.env`, `data/*.db`, `reports/*.md`, `reports/*.json`, `reports/*.html`, `__pycache__/`, `.venv/`, `.pytest_cache/` (el `.gitignore` real además excluye `.ruff_cache/`, `.coverage`, `*.egg-info/` y `validation/results/`, `validation/ground-truths/`).
- **0.1.6. `.env.example`:** ver subtarea 0.4. No copiar secretos.

Docker **no** se implementa aquí (TASK-07). Sí dejar `data/` y `reports/` listos.

---

### Subtarea 0.2: Modelado de Datos y Persistencia

- **0.2.1. Modelos (SQLModel).** UUIDs como `str` (UUID4) salvo `RawMetadataItem.id` autoincrement. Timestamps timezone-aware UTC.
  - **Modelos posteriores añadidos fuera de TASK-00** (especificados en sus propias tasks): `Scope` (TASK-10), `FindingFeedback` + enum `FeedbackVote` + helper `severity_rank` (TASK-13), `WebhookConfig` + `WebhookDelivery` + enum `WebhookDeliveryStatus` (TASK-15). El campo `Run.run_ref` (TASK-15) tampoco está en la tabla de abajo.

  **`Run`**
  - `id` PK
  - `target_input` Text (JSON serializado de la lista de targets)
  - `allowed_scope` Text (JSON de dominios autorizados)
  - `scope_confirmed` Boolean default `False`
  - `reasoning_depth` Enum `brief|standard|detailed` default `standard`
  - `status` Enum `pending|running|completed|failed|aborted`
  - `started_at` DateTime UTC
  - `completed_at` Optional[DateTime]
  - `total_assets` Integer default 0
  - `total_findings` Integer default 0
  - `error_message` Optional[Text]
  - `executive_summary` Optional[Text] — párrafo ejecutivo del nodo `SynthesizeReportSummary` (TASK-05); `NULL` si los agentes no corrieron. Añadido en la auditoría post-MVP para que el reporte (TASK-04, 4.1.2) lo consuma en cualquier re-export.

  **`Asset`**
  - `id` PK
  - `run_id` FK → `Run.id` indexed
  - `source_url` String
  - `final_url` String
  - `content_type` String
  - `file_hash_sha256` String indexed
  - `file_size_bytes` Integer
  - `extraction_status` Enum `ok|skipped|failed`
  - `skip_reason` Optional[String] (`unsupported_type`, `too_large`, `out_of_scope`, `duplicate_hash`, `empty_body`)
  - `error_message` Optional[String]
  - `discovered_at` DateTime UTC
  - Índice compuesto `(run_id, file_hash_sha256)`

  **`RawMetadataItem`**
  - `id` Integer PK autoincrement
  - `asset_id` FK → `Asset.id` indexed
  - `namespace` String (`exif`, `xmp`, `pdfinfo`, `iptc`, `http`, `html`, `js`)
  - `key` String
  - `value` String (siempre texto sanitizado; nunca bytes)

  **`Finding`**
  - `id` PK
  - `run_id` FK indexed
  - `asset_id` FK indexed
  - `finding_type` Enum de los 5 tipos
  - `field_source` String (si hay varios orígenes deduplicados: unidos con ` | `)
  - `evidence_snippet` Text
  - `dedup_signature` String indexed — `sha256(asset_id:finding_type:evidence_snippet.strip().lower())`
  - Unique constraint `(asset_id, dedup_signature)`
  - `detector_method` Enum `rule|heuristic|agent`
  - `confidence` Enum `high|medium|low`
  - `severity` Optional Enum — **`NULL` hasta clasificar**
  - `severity_justification` Optional[Text]
  - `impact_analysis` Optional[Text]
  - `remediation_advice` Optional[Text]
  - `reproduction_steps` Optional[Text] (JSON array serializado o texto con saltos; el exportador JSON lo materializa como lista)
  - `title` Optional[String] — título de una línea redactado por el agente (TASK-05); `NULL` → el reporte usa la plantilla por tipo. Añadido en la auditoría post-MVP.
  - `agent_model_used` Optional[String]
  - `created_at` DateTime UTC

  **`AgentLog`**
  - `id` PK
  - `run_id` FK indexed
  - `finding_id` FK → `Finding.id`
  - `prompt_tokens` Integer
  - `completion_tokens` Integer
  - `model_name` String
  - `latency_ms` Integer
  - `raw_response` Text (salida estructurada; no guardar el PDF ni el prompt completo si contiene secretos de API)
  - `created_at` DateTime UTC

- **0.2.2. Engine asíncrono:** `sqlite+aiosqlite:///./data/metatracer.db` (overridable). `init_db()` crea tablas con `PRAGMA foreign_keys=ON` (escuchada por evento en **cada** conexión, no solo al iniciar). `create_db_engine()` crea el directorio padre del archivo SQLite si no existe (`data/` está en `.gitignore`; un clone fresco no lo trae). Schema listo para migrar a PostgreSQL más adelante (no usar tipos exclusivos de SQLite en los modelos).
  - `init_db()` además aplica **ALTER TABLE ... ADD COLUMN** para columnas ausentes (nullable, o NOT NULL con default Python como `Run.run_ref` de TASK-15, que se añade nullable para poder migrar una tabla no vacía). Postura explícita: sin Alembic en el MVP; columnas NOT NULL sin default no se migran automáticamente (TASK-13).
- **Desde TASK-23 (Eje B, 2026-09-17):** `create_db_engine` también acepta `postgresql+asyncpg` (único driver Postgres soportado; `postgresql://` pelado o backends desconocidos se rechazan con `ValueError`). En Postgres, `init_db()` instala `CREATE EXTENSION IF NOT EXISTS vector` y corre las **migraciones Alembic empaquetadas** (`db/migrations/`) hasta head en un worker thread; SQLite conserva el bootstrap legacy. No usar `str(engine.url)` para reconstruir la URL: enmascara la contraseña (`***`); usar `render_as_string(hide_password=False)`.
  - **Concurrencia (desde TASK-23):** `METATRACER_MAX_CONCURRENT_RUNS` (default 1) sustituye el lock de un solo scan por un `asyncio.Semaphore(N)`; con N=1 la semántica 409 es idéntica. Nota operativa: el rate limit por dominio se instancia **por run**, así que N runs concurrentes multiplican el RPS efectivo contra el mismo dominio. El lock de watch por scope (TASK-22) es de fichero por proceso y sigue ortogonal.
- **0.2.3. Repositorios:** `RunRepository`, `AssetRepository`, `RawMetadataRepository`, `FindingRepository`, `AgentLogRepository`. CRUD mínimo + `list_by_run`. No lógica de negocio aquí. Repositorios añadidos en versiones posteriores: `ScopeRepository` (TASK-10), `FeedbackRepository` (TASK-13), `DashboardRepository` (TASK-11, agregaciones de solo lectura), `WebhookConfigRepository` + `WebhookDeliveryRepository` (TASK-15).

---

### Subtarea 0.3: Safety Core

- **0.3.1. `ScopeValidator`:**
  - Normalizar: quitar `http://`, `https://`, path, query, fragment y puerto. Lowercase. Quitar el punto final.
  - Matching: `host == domain` **o** `host.endswith("." + domain)`. `evil-target.com` **no** matchea `target.com`.
  - Wildcard `*.target.com` matchea subdominios, **no** el apex (salvo que el apex esté también en la lista).
  - Sin Public Suffix List en el MVP; documentar la limitación (`foo.co.uk` se trata como dominio opaco).
  - Rechazar si el host no está cubierto por `allowed_scope`.

- **0.3.2. `NetworkSafetyGuard` (anti-SSRF):**
  - Antes de cada petición: resolver DNS y comprobar **todas** las IPs (A y AAAA).
  - Bloquear:
    - Loopback: `127.0.0.0/8`, `::1`
    - Unspecified: `0.0.0.0/8`, `::`
    - RFC 1918: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
    - Link-local: `169.254.0.0/16`, `fe80::/10` (incluye metadata cloud `169.254.169.254`)
    - CGNAT: `100.64.0.0/10`
    - Unique local IPv6: `fc00::/7`
    - Multicast: `224.0.0.0/4`, `ff00::/8`
  - Lanzar `SecurityViolationError` **antes** de abrir el socket.
  - Re-verificar el host de cada hop de redirect (TASK-01 usa esto).
  - Limitación conocida (TOCTOU / DNS rebinding): se acepta en el MVP; no hace falta pin de IP en el transporte, pero la guarda debe llamarse inmediatamente antes de cada request.

- **0.3.3. Confirmación de scope:**
  - Si `scope_confirmed` es `False`, el orquestador (y cualquier API pública de scan) aborta con `ScopeNotConfirmedError`.
  - `METATRACER_ALLOW_LOOPBACK` default `false`. Solo tests (TASK-07) pueden activarlo. No existe flag de CLI `--insecure` en la distribución por defecto.

- **0.3.4. Wrapper HTTP:** todo cliente HTTP del proyecto (incluido el crawler) debe pasar por un único helper (`safe_httpx_request` o equivalente) que ejecute scope + guarda. Prohibido usar `httpx` crudo desde extractores/servicios. `core/safety/http.py` es el **único** módulo con cliente HTTP de ingesta; re-exporta `HttpTransportError` para que los llamadores capturen errores de transporte sin importar la librería.
  - **Única excepción aprobada (TASK-15, v2.2):** `api/webhooks.py` importa `httpx` localmente para el envío **de salida** a endpoints de webhook (Slack/Discord/Teams). Ese cliente es un egress de operador hacia terceros, no un asset del scope del run, por lo que **no** pasa por `safe_httpx_request` (que exigiría scope confirmado y rechazaría el host). En su lugar usa su propio cliente restringido: HTTPS-only, sin redirects, timeouts cortos, body nunca leído, y re-validación anti-SSRF con el mismo `NetworkSafetyGuard` antes del socket (regla 7 aplicada también al egress).

---

### Subtarea 0.4: Config, logging y excepciones

- **0.4.1. `Settings` (pydantic-settings), prefijo `METATRACER_`:**

  | Variable | Default | Uso |
  | :--- | :--- | :--- |
  | `DATABASE_URL` | `sqlite+aiosqlite:///./data/metatracer.db` | Engine |
  | `LLM_API_KEY` | vacío | Kimi / Moonshot |
  | `LLM_BASE_URL` | vacío | Compatible OpenAI-API |
  | `LLM_MODEL` | vacío | Modelo fuerte |
  | `FAST_MODEL` | vacío | Modelo barato |
  | `LOG_LEVEL` | `INFO` | Logging |
  | `MAX_ASSETS_PER_RUN` | `50` | Tope de descargas |
  | `MAX_FILE_BYTES` | `52428800` (50 MB) | Tope por archivo |
  | `RATE_LIMIT_RPS` | `2` | Req/s por dominio |
  | `API_RATE_LIMIT_PER_MINUTE` | `120` | Req/min por IP en el borde de la API; `0` lo desactiva (v2.3) |
  | `MAX_REQUEST_BODY_BYTES` | `5242880` (5 MB) | Tope del body de peticiones HTTP a la API (v2.3) |
  | `ALLOW_LOOPBACK` | `false` | Solo tests |
  | `BIND_HOST` | `127.0.0.1` | API local; Docker usará `0.0.0.0` |

- **0.4.2. Logging:** `logging` stdlib. Formato con timestamp UTC, nivel, logger, mensaje. Si hay `run_id` en el contexto, incluirlo. Sin `print` en librería.
- **0.4.3. Excepciones** (todas subclase de `MetaTracerError`):
  - De TASK-00: `OutOfScopeError`, `RedirectOutOfScopeError`, `SecurityViolationError`, `ScopeNotConfirmedError`, `ExtractionError`, `UnsupportedAssetError`, `AgentUnavailableError`.
  - Añadidas en versiones posteriores: `RunNotFoundError` (TASK-08), `ScopeNotFoundError` + `AmbiguousRunError` (TASK-10, CLI show/API), `ScanAlreadyRunningError` (TASK-06, lock de un solo scan; API la mapea a 409).

---

## 3. Fuera de alcance de esta tarea

- Extractores, detectores, agentes, reportes, CLI real, Web UI, Dockerfile.
- PostgreSQL, migraciones Alembic, autenticación de usuarios.
- Public Suffix List, pin de IP anti-rebinding.

---

## 4. Tests mínimos (escribir ahora)

- `tests/unit/test_scope_validator.py`
- `tests/unit/test_network_safety_guard.py`
- `tests/unit/test_settings.py` (defaults; `ALLOW_LOOPBACK` es false)

Cubrir: matching de subdominio vs `evil-target.com`, wildcard, bloqueo de `127.0.0.1` / `192.168.1.1` / `169.254.169.254`, y que el engine crea las tablas.

---

## 5. Criterios de Aceptación (DoD)

- [x] `pip install -e ".[dev]"` funciona; Ruff pasa sobre `src/` y `tests/`.
- [x] `init_db()` crea todas las tablas, FKs e índices (incluido unique de `dedup_signature` por asset).
- [x] Una URL cuyo host no está en scope lanza `OutOfScopeError` y **no** realiza petición HTTP.
- [x] Un host que resuelve a loopback, RFC 1918 o link-local lanza `SecurityViolationError` antes del socket.
- [x] `scope_confirmed=False` produce `ScopeNotConfirmedError`.
- [x] `ALLOW_LOOPBACK` default es `false`.
- [x] `Finding.severity` es nullable en el schema.
