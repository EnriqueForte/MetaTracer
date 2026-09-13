# TASK-19: Import de scope desde archivo (v2.2)

**Módulo:** Integraciones — portabilidad de la gestión de scopes
**Referencia PRD:** [Timeline y roadmap](../features/10-timeline-and-roadmap.md), [Interfaces](../features/06-interfaces.md)
**Dependencias:** TASK-00 … TASK-18 (v1.0–v2.2 cerradas)
**Estado:** **Implementada y validada 2026-09-13** — módulo `scopes/portable.py` (parse + import + export), CLI `scope import`/`scope export` (grupo Typer), API `POST /api/scopes/import`. Verificado: `pytest -m "not e2e"` **475 passed** + `ruff check src tests` limpio + guardrail `ci-check.ps1` OK (cobertura ≥85%).

---

## 1. Objetivo técnico

TASK-10 creó la **entidad `Scope`** (conjunto reutilizable de dominios
autorizados) con CRUD por API/Web UI, pero el operador solo puede darla de
alta **a mano**, un scope a la vez. La fase v2.2 *Integraciones* listó
**"import scope"** como entregable: poder **traer scopes desde un archivo**,
igual que TASK-17 hizo portables los precedentes del RAG.

Qué aporta de producto:

- El operador recibe de un compañero/cliente un *engagement scope* en un
  archivo (p. ej. el listado de dominios que entrega el programa de bug bounty
  o el cliente al empezar el pentest) y lo **importa en un paso** en vez de
  teclear N dominios en el formulario.
- Permite **backup/restore y portabilidad entre máquinas** de la gestión de
  scopes sin copiar la BD completa (que incluye runs, assets, raw metadata,
  webhooks: mucho dato operativo). La entidad `Scope` es **solo los dominios y
  su nombre/descripción**, nada más — el archivo de import es exactamente ese
  contrato mínimo.
- Es coherente con el resto de v2.2: *KB portable* (TASK-17) y *exports
  bounty* (TASK-18) ya demuestran el patrón archivo ↔ CLI ↔ API; esta task
  lo aplica al dominio de scopes.

Preservación de invariantes:

- **Cero red** (regla 1): el import es una operación de archivo local, como el
  export/import de la KB. No hay HTTP en este flujo.
- **Cero bytes de archivos** (regla 3): el formato es JSON de texto con
  dominios ya normalizados; nunca se persisten archivos ni metadata cruda.
- **El import no inventa**: `name`, `description` y cada dominio se validan
  con las mismas reglas que `ScopeCreate` (TASK-10); lo que no pasa se
  **rechaza con error**, nunca se reasigna ni se adivina.
- **Idempotente y no destructivo**: importar el mismo archivo dos veces no
  duplica scopes ni pisa los existentes. El import **no borra** nada.

---

## 2. Subtareas

### 19.1 Contratos

**Formato del archivo de import** (JSON, UTF-8, en un módulo nuevo
`metatracer/scopes/portable.py` — espejo de `metatracer/knowledge/portable.py`):

```json
{
  "format_version": 1,
  "scopes": [
    {
      "name": "acme-2026",
      "description": "Acme Corp engagement (optional)",
      "domains": ["target.com", "*.target.com", "static.target.com:8080"]
    }
  ]
}
```

Reglas del archivo (contrato cerrado):

- `format_version` **obligatorio**, entero; cualquier otro valor →
  `ValueError` descriptivo (p. ej. `unsupported format_version 2`).
- `scopes` **obligatorio**, lista (puede ser `[]`, válido — import de 0).
- Cada entrada: `name` (str, `1..64` chars tras strip, **único**
  case-insensitive), `description` (`str | None`, opcional), `domains`
  (lista no vacía de str).
- Cada dominio se normaliza con `normalize_host` (minúsculas, sin
  scheme/puerto/path, comodines `*.` permitidos) **exactamente igual** que
  `ScopeCreate` de TASK-10: entradas vacías o que normalizan a `""` se
  descartan; si al final `domains` quedase vacío → error para esa entrada
  (un scope sin dominios no audita nada).
- **Nada más** se admite en el archivo: ni `id`, ni `created_at`, ni campos
  desconocidos (los campos extra se rechazan con error para no aceptar
  silenciosamente formatos no soportados).

### 19.2 Módulo `metatracer/scopes/portable.py`

Paquete nuevo `metatracer/scopes/` (junto a `reports/`, `knowledge/`),
**0 dependencias nuevas** (stdlib `json`/`dataclasses`):

- `@dataclass(frozen=True) ScopeEntry` — `name: str`, `description: str | None`,
  `domains: tuple[str, ...]` (ya normalizados).
- `def parse_scopes_file(source: Path) -> list[ScopeEntry]`:
  - Lee el JSON, valida `format_version == 1` y estructura (`scopes` lista).
  - Normaliza dominios con `normalize_host` y descarta vacíos; entrada sin
    dominios válidos → `ValueError` con detalle (p. ej.
    `entry 2 'acme': no valid domains`).
  - `name` vacío/duplicado en el **mismo archivo** → `ValueError` con detalle
    (p. ej. `entry 3: duplicate name 'acme-2026'`).
  - Devuelve la lista; un archivo inexistente o JSON inválido lanza el error
    estándar de IO/JSON (el CLI lo muestra con mensaje claro).
- `async def import_scopes(session_factory, source: Path) -> ScopeImportResult`:
  - ``(o devuelve un int n)``: recorre las entradas y, para cada una, comprueba
    `ScopeRepository.get_by_name(name)`; **si ya existe lo omite** (idempotente);
    si no, crea un `Scope` nuevo con `domains=json.dumps(entry.domains)`.
  - Devuelve `ScopeImportResult(imported: int, skipped: int)` (dataclass); no
    existe el scope → no falla, se cuenta como `skipped`.
  - **No borra nada**; el orden del archivo no importa (cada entrada es
    independiente, una colisión de nombre no aborta el resto).
- `@dataclass(frozen=True) ScopeImportResult` — `imported: int`, `skipped: int`.

Reutilización: `normalize_host` vive en `metatracer/core/safety/scope.py`
(ya importable); `ScopeRepository` en `metatracer/db/repositories.py`.

### 19.3 Cambios `metatracer/api/scopes.py` (fleco mínimo)

La normalización de `domains` en `ScopeCreate`/`ScopeUpdate` ya usa
`normalize_host` — **sin cambios** ahí. Solo se añade el endpoint de import
(subtarea 19.5) al router existente.

### 19.4 CLI (`metatracer/cli/main.py`)

Dos subcomandos nuevos bajo un grupo `scope` (Typer, alineado con `kb`):

- `metatracer scope import --file scopes.json`:
  - Valida que el archivo exista → error claro si no.
  - Llama a `import_scopes`, imprime con Rich
    `Imported <n> scopes (<m> skipped: already exist)`.
  - `ValueError` del parse/import → error claro y exit 1.
  - Idempotente: re-importar el mismo archivo no duplica.
- `metatracer scope export --file scopes.json` (**opcional, recomendado** si
  el coste es bajo): espejo de `kb export` — vuelca todos los scopes al
  formato de la subtarea 19.1. Si se incluye, el par export/import cierra el
  ciclo de portabilidad; si no, el import basta para el caso de "traer scopes
  de un compañero".

No añadir dependencias (Typer/Rich ya están). El grupo usa el patrón
`_execute_scope_import(source)` (engine up → import → engine down) igual que
`_execute_kb_import`.

### 19.5 API (`metatracer/api/scopes.py`, router existente)

- `POST /api/scopes/import` → acepta el archivo subido (`UploadFile`), lo
  escribe a temp y llama a `import_scopes`; responde
  `ScopeImportResponse { "imported": n, "skipped": m }` (201).
- Sin archivo → 422. `ValueError` del parse → 422 con el detalle (igual
  patrón que `import_kb_endpoint` de TASK-17).
- **Sin diálogo de confirmación en BD**: el import inserta; el usuario puede
  revertir con un `DELETE /api/scopes/{id}` si se equivoca.
- El resto del router (CRUD) **no cambia**.

Wiring en `app.py`: ninguno nuevo (el router ya está registrado).

### 19.6 Web UI (opcional, bajo coste)

- En `/scopes` (`metatracer/api/templates/scopes.html`), botón "Import" junto a
  la tabla que sube un `.json` a `POST /api/scopes/import` y refresca la tabla.
- Solo si el patrón de TASK-17 lo permite sin añadir JS complejo; el CRUD y el
  flujo CLI/API son el DoD principal.

### 19.7 Safety y persistencia

- **Cero red**: import local, sin HTTP saliente (no aplica el egreso).
- **Cero bytes**: el archivo es JSON de texto; nunca se persiste el archivo ni
  metadata cruda en la BD (solo `name`/`description`/`domains`).
- **Cero rastro de secretos**: `name`/`description`/`domains` se sanitizan
  antes de cualquier log (reusar `sanitize_for_log`); los errores del parser
  incluyen solo el nombre de la entrada, nunca el contenido crudo del archivo.
- **No relajar el gate de scope**: el import solo crea `Scope` rows
  (normalizados); el matching en el scan sigue exigiendo `ScopeValidator`.
- El `Scope` importado se comporta igual que uno creado a mano: el run copia
  `domains` a `Run.allowed_scope` (sin FK).

---

## 3. Fuera de alcance

- Import desde formatos no-JSON (CSV de dominios, TXT plano, HackerOne scope
  export, ZIP, gzip).
- Sync bidireccional / merge con conflictos: ante `name` duplicado **se omite**
  la entrada, no se actualiza ni se pide confirmación.
- Soporte de comodines `*.` en la UI (sigue en TASK-10 out-of-scope).
- Migración entre `format_version`s: solo se soporta la 1.
- Autenticación / multi-usuario (sigue sin auth; proteger por bind).

---

## 4. Tests mínimos

- `tests/unit/test_scope_portable.py`:
  - `parse_scopes_file` lee un archivo válido y normaliza dominios
    (scheme/puerto/path/case).
  - `parse_scopes_file` descarta entradas vacías y rechaza entrada sin
    dominios con `ValueError` (no la reasigna).
  - `parse_scopes_file` rechaza `format_version` desconocido, `name` vacío y
    `name` duplicado en el mismo archivo.
  - `import_scopes` inserta los scopes nuevos; re-importar (idempotente) no
    duplica (`imported=0, skipped=N`).
  - `import_scopes` con un scope que ya existe no lo pisa (omite).
- `tests/integration/test_api_scope_import.py`:
  - `POST /api/scopes/import` con un archivo válido inserta filas y responde
    `{"imported": n, "skipped": m}`.
  - Re-importar por API no duplica (idempotencia).
  - Import con `format_version`/estructura inválida → 422 con detalle (no 500).
  - Sin archivo → 422.
- CLI: `tests/integration/test_cli_scope_import.py` (o dentro del test de CLI
  de scopes):
  - `metatracer scope import --file <válido>` devuelve exit 0 e imprime counts.
  - `metatracer scope import --file <inexistente>` devuelve exit 1 con error claro.
  - Archivo inválido → exit 1 con el detalle del `ValueError`.
- Suite completa en verde: `pytest -m "not e2e"` y `ruff check src tests`
  (guardrail de TASK-16: `ci-check.ps1`).

---

## 5. Criterios de aceptación (DoD)

- [ ] Un operador recibe un `scopes.json` y `metatracer scope import --file
      scopes.json` crea los scopes; los dominios quedan normalizados.
- [ ] Importar el mismo archivo dos veces no duplica (idempotencia por
      `name` case-insensitive) y no pisa scopes existentes.
- [ ] Import con `format_version`/estructura/`name` duplicado/entrada sin
      dominios → error claro, sin insertar nada incorrecto (no reasigna).
- [ ] `POST /api/scopes/import` permite el mismo flujo por Web UI/curl y
      devuelve counts; sin archivo → 422.
- [ ] Los scopes importados se usan igual que los creados a mano en un scan
      (`scope_id` → dominios resueltos en `Run.allowed_scope`).
- [ ] Cero dependencias nuevas; cero red; cero bytes en archivo/BD (solo
      metadata de contrato).
- [ ] `pytest -m "not e2e"` en verde y `ruff check src tests` limpio,
      validado con el guardrail de TASK-16 (`scripts/ci-check.ps1`).