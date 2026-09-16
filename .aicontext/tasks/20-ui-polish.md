# TASK-20: UI polish y accesibilidad (v2.3)

**Módulo:** v2.3 Performance & UI polish — pulido de interfaz y accesibilidad
**Referencia PRD:** [Interfaces](../features/06-interfaces.md), [Requisitos técnicos](../features/07-technical-requirements.md)
**Dependencias:** TASK-00 … TASK-19 (v1.0–v2.2 cerradas; slice v2.3 en curso)
**Estado:** **Cerrada 2026-09-16** — la mitad de rendimiento del slice v2.3 (rate limit de API y body cap, commits `feat(perf)`) y el pulido de UI (20.1–20.5) quedan completos y verificados. Suite en verde, `ruff` limpio y cobertura ≥85% (guardrail TASK-16), validado localmente con `ci-check.ps1`.

**Progreso de implementación (2026-09-16):**
- **20.1 ✅** matriz de estados por página completada (ver abajo) y huecos detectados.
- **20.2 ✅** helpers compartidos `window.MetaTracerUI` (`readError`/`truncate`/`formatWhen`) en `base.html`; `base.html`, `history.html`, `dashboard.html`, `scopes.html`, `run.html` delegados, sin duplicados.
- **20.3 ✅** modal de scope e drawer de finding con focus entry/restore + trampa de Tab + Escape; filas de findings activables por Enter; `role="dialog"`/`aria-modal`/`aria-labelledby`.
- **20.4 ✅** tests creados (`test_a11y_focus.py`, `test_history_page.py`, `test_scopes_page.py`, ampliación de `test_feedback_page.py`) — **suite ejecutada y en verde por el operador**.
- **20.5 ✅** cierre del slice: README de tasks y timeline marcan v2.3 cerrada; walkthrough sin cambios (el pulido no altera el recorrido de la demo).

---

## 1. Objetivo técnico

El slice v2.3 se anunció con tres frentes: (1) rate limit de API, (2) límite de body, (3) *"pulido de UI (accesibilidad, estados de carga, empty states, consistencia de errores)"*. Los dos primeros están cerrados y testeados (`test_api_performance.py`, 6 passed). El tercero existe **de facto** en las plantillas (todas renderizan loading/empty/error básicos) pero **nunca se definió como backlog verificable**.

Esta task convierte esa línea en subtareas con DoD comprobable, audita cada página contra una matriz de estados y endurece la accesibilidad (foco, ARIA, teclado) con tests automáticos. No introduce dependencias nuevas (sin axe-core en runtime; las aserciones a11y se hacen con DOM/HTML en los tests de página existentes).

Superficie auditada (`src/metatracer/api/templates/`):

| Plantilla | Ruta | Estados ya presentes |
| :--- | :--- | :--- |
| `index.html` | `/` | error de validación, modal de confirmación, busy (starting) |
| `run.html` | `/runs/{id}` | loading, unknown run, failed, live progress, findings error, zero findings, drawer |
| `history.html` | `/runs` | loading, error, empty |
| `dashboard.html` | `/dashboard` | loading, error, empty global |
| `scopes.html` | `/scopes` | loading, error, empty, busy (import), feedback de import |
| `base.html` | todas | skip-link, campana de notificaciones (empty/error) |

---

## 2. Subtareas

### 20.1 Inventario de estados por página

- Para cada fila de la tabla anterior, definir la matriz **loading · empty · error(4xx/5xx) · not-found · busy** y marcar huecos.
- Casos a verificar explícitamente:
  - `run.html`: estado "findings no cargables" **distinto** de "cero findings" (ya existe `findingsError` vs `findings.length === 0` — confirmar con test).
  - `index.html`: 409 (scan en curso) y 403 (scope rechazado) ya se muestran; añadir estado para el fallo de guardado de scope (sin romper el flujo manual).
  - `scopes.html`: mensaje de import 413 (ya existe), y confirmar que un 500 del import deja la lista visible.
- Entregable: tabla de cobertura comentada en el propio template o en un docstring; los huecos detectados se cubren en las subtareas 20.2/20.3.

**Matriz de cobertura (resultado 2026-09-16):**

| Página | loading | empty | error 4xx/5xx | not-found | busy | Huecos detectados |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/` (`index.html`) | n/a (form estático) | n/a | ✅ (`error`, incl. 409/403/429) | n/a | ✅ `starting` | **20.3**: modal sin foco inicial/retorno; sin `Escape` |
| `/runs/{id}` (`run.html`) | ✅ | ✅ zero-findings | ✅ `loadError` + `findingsError` | ✅ | ✅ SSE progress | **20.3**: drawer sin foco/trampa/retorno; filas sin soporte teclado; faltan `role="dialog"`/`aria-modal` |
| `/runs` (`history.html`) | ✅ | ✅ | ✅ + Retry | n/a | n/a | **20.2**: `readError`/`formatWhen` duplicados |
| `/dashboard` | ✅ | ✅ global | ✅ + Retry | n/a | n/a | **20.2**: `readError`/`truncate` duplicados |
| `/scopes` | ✅ | ✅ | ✅ + Retry + import 413/500 | n/a | ✅ `importBusy` | **20.2**: `readError`/`formatWhen` duplicados |
| `base.html` (campana) | ✅ | ✅ | ✅ | n/a | n/a | **20.2**: `readError`/`truncate` duplicados |

**Decisión de diseño (20.2):** `readError` (mensaje `{detail}` de FastAPI + fallback genérico con HTTP status), `truncate` y `formatWhen` viven **una sola vez** en `window.MetaTracerUI` en `base.html`; cada componente Alpine delega con una línea. No hay dependencias nuevas.

### 20.2 Consistencia de errores

- Extraer el helper repetido `readError(response)` (hoy copiado en 5 bloques Alpine: base, history, dashboard, run, scopes) a un fragmento compartido en `base.html` (p. ej. un mixin Alpine `errorHelpers`), manteniendo el contrato `{ detail }` de FastAPI.
- Convención única de mensaje: `"Could not <recurso> (HTTP <status>)."` + botón "Retry" donde tenga sentido (listas y dashboard), manteniendo el inglés de UI (contrato de idiomas).
- Asegurar que los 429 del rate limiter (v2.3) muestran mensaje legible en todas las superficies que escriben (index, scopes) — ya se hizo en `scopes.html`/`index.html`; verificar `run.html`/dashboard (solo lectura).

### 20.3 Accesibilidad

- **Focus management**:
  - Modal de confirmación de scope (`index.html`): foco inicial en el botón "Cancel" (o el checkbox), retorno del foco al "Start scan" al cerrar; `aria-modal` ya está.
  - Drawer de finding (`run.html`): foco inicial dentro del drawer al abrir, trampa de foco (tab), retorno al elemento que lo abrió al cerrar; `Escape` ya cierra (`@keydown.escape.window`).
- **ARIA**: verificar `aria-expanded`/`aria-controls` en la campana (ya presentes) y añadir `aria-live="polite"` donde una acción asíncrona cambia el contenido sin foco (import de scopes, feedback).
- **Teclado**: la tabla de findings navega por click; añadir soporte de `Tab`/`Enter` (o al menos `tabindex="0"` + Enter) en las filas con `@click="select"`.
- **Contraste**: revisar pares sobre `bg-slate-950`/`bg-slate-900` con texto `text-slate-400/500` (WCAG AA para texto pequeño); ajustar clases si algún par queda por debajo.
- Skip-link ya existe en `base.html`; confirmar que el `#main-content` recibe foco en la navegación (test).

### 20.4 Tests de página y accesibilidad

Sin dependencias nuevas: aserciones sobre el HTML renderizado y el estado Alpine vía la API mockeada.

- `tests/integration/test_dashboard_page.py`, `test_notifications_page.py`, `test_feedback_page.py`, `test_scopes_page.py` (nuevo) y `test_history_page.py` (nuevo):
  - Estado vacío: la página renderiza el empty state cuando `/api/...` devuelve lista vacía.
  - Estado error: mock de respuesta 500 en el endpoint → el bloque de error aparece con texto y botón Retry.
  - `run.html`: 404 de run → "Run not found"; findings 500 → `findingsError` visible; cero findings → mensaje verde dedicado.
- `tests/integration/test_a11y_focus.py` (nuevo): assert de presencia de `aria-modal`, `aria-expanded`, `aria-controls`, `role="alert"`, skip-link y que el modal empieza con el foco esperado (via `autofocus` o JS de init).
- Suites existentes siguen verdes: `pytest -m "not e2e"` + `ruff check src tests` + cobertura ≥85% (guardrail TASK-16).

### 20.5 Cierre del slice v2.3

- Actualizar `tasks/README.md` y `features/10-timeline-and-roadmap.md` con TASK-20 cerrada y los conteos finales del slice (suite total + cobertura).
- Actualizar `walkthrough.md` solo si el pulido cambia el recorrido de la demo (no se espera).
- Confirmar el árbol de git limpio (incluida la sincronización del doc TASK-00 pendiente de commitear).

---

## 3. Fuera de alcance

- Framework de diseño nuevo, tema claro o dark-mode toggle.
- Migrar Tailwind CDN a un build estático/vendorizado (se anota como deuda en el layout de TASK-00, no se ejecuta aquí).
- i18n / localización de la UI (se mantiene inglés, contrato de idiomas).
- Cambios de layout o navegación que no respondan a un hueco de la matriz 20.1.

---

## 4. Tests mínimos

- `test_history_page.py`: empty state y error state de `/api/runs`.
- `test_scopes_page.py`: empty state, error state y 413 del import (existe el manejo en `scopes.html`; falta assert de página).
- `test_a11y_focus.py`: `aria-*`, `role="alert"`, skip-link, foco inicial del modal.
- `run.html`: cero findings ≠ findings error (ampliar `test_feedback_page.py` u otro de run).
- Suite completa del slice: `pytest -m "not e2e"` verde + `ruff` limpio + `ci-check.ps1` OK.

---

## 5. Criterios de aceptación (DoD)

- [x] La matriz 20.1 está completa (ningún hueco sin cubrir o explícitamente anotado como no aplicable).
- [x] `readError`/Retry compartidos: una sola implementación en `base.html`, sin duplicados en las 5 páginas.
- [x] Modal de scope y drawer de finding gestionan foco (entrada, trampa y retorno).
- [x] Contraste de los pares principales cumple AA; skip-link navegable.
- [x] Tests de página cubren empty/error/busy/not-found de las 5 páginas + asserts a11y en `test_a11y_focus.py` — suite ejecutada y en verde.
- [x] `pytest -m "not e2e"` verde, `ruff check src tests` limpio, cobertura ≥85% (`ci-check.ps1`) — validado localmente por el operador.
- [x] README de tasks y timeline marcan v2.3 cerrada con conteos finales.