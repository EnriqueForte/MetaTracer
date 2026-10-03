# TASK-35: Mejoras de UI/UX de la Web V2 (v3.2)

**Módulo:** Web V2 (`web/`, Next.js + React). El bloque 35.7 (triage) toca además `db/`, `api/`, `cli/`, `reports/` y `services/watch.py`. No toca Jinja/Alpine (V1).
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § 3; [v2-ui-refresh.md](../architecture/v2-ui-refresh.md), [v2-visual-direction.md](../architecture/v2-visual-direction.md), [v2-frontend-architecture.md](../architecture/v2-frontend-architecture.md), [feature-parity-matrix.md](../migrations/feature-parity-matrix.md)
**Dependencias:** TASK-26. Los bloques 35.4 y 35.5 que tocan el API dependen de TASK-28 (abort) y TASK-30 (borrado).
**Agente recomendado:** `v2-ui-engineer` (diseño previo con `ui-architect` para 35.3 y 35.4).
**Estado:** **Pendiente** (planificada 2026-10-03).

---

## 1. Objetivo técnico

La Web V2 tiene paridad de pantallas con la V1 (~95%), pero el triage diario tiene fricción: filtros sin estado visible, notificaciones que no llevan al run, acciones de operator visibles para viewers. Además, el código se aparta de la arquitectura documentada (sin TanStack Query, Zod ni tipos generados). Esta task agrupa todas las mejoras de UI/UX de la auditoría en cinco bloques implementables por orden.

Principios: inglés en la UI; render seguro (sin `dangerouslySetInnerHTML`, URLs vía `safeUrl`); CSP sin CDN; severidad siempre con texto + color; `prefers-reduced-motion` respetado; las acciones de mutación se ocultan para viewers.

## 2. Subtareas

### 35.1 Arreglos rápidos de triage y paridad (S)

- **Filtros visibles:** variante `toggle` en `ui/button.tsx` con estilo `aria-pressed:` (borde y texto accent), equivalente a `metatracer.css` L185–188 de la V1. Aplicar en `findings-panel.tsx` y `history-view.tsx`.
- **Filtro `Unclassified`** de severidad en `findings-panel.tsx`.
- **Campana con enlace:** `lib/api/browser.ts` conserva `run_id` y `created_at` de las notificaciones; cada item de `app-shell.tsx` es un `Link` a `/runs/{run_id}` con hora relativa.
- **Copy del código de invitación** en `users-view.tsx`, con confirmación "Copied" (mismo patrón que Copy evidence).
- **Gating por rol:** ocultar el drawer de feedback y cualquier mutación a los viewers (rol desde `/api/auth/me` en el shell, expuesto por contexto).
- **Wizard:** si hay `scope_ids` seleccionados, deshabilitar el input de dominios manuales con nota "Using saved scopes — manual domains are ignored" (y al revés).
- **Modal de scope** migrado a `ui/dialog.tsx` (Radix) con focus trap.
- **Errores de import de scopes** específicos (tamaño, JSON inválido, `detail` del API) como en la V1.
- **Teclado:** `Space` además de `Enter` abre la fila de finding.
- **Aviso ético:** "Authorized use only" con tooltip o línea expandible que muestre el texto completo.
- **Unificar** empty states de findings e history con `EmptyState` de `ui/states.tsx`.

### 35.2 Cambios sin commit de 2026-10-03 (S)

- `AssetFindings` (`findings-panel.tsx`): agrupar sobre la lista **filtrada**, conservar el orden del API y hacer cada badge clicable para abrir el sheet del finding; sección colapsable. Si no se completa, retirar el bloque antes del commit.
- `run-progress.tsx`: "Recent progress" solo si hay ≥2 mensajes distintos; no repetir el mensaje visible.
- `globals.css`: animar `.mt-stage-asset` solo al cambiar de etapa (no en bucle) y sustituir `border-radius: 999px` del pill ético por el radio `md` del design system.

### 35.3 Productividad del operador (M)

- **Filtros en la URL** de la vista de run (`?severity=&type=&confidence=&q=&asset=`), restaurados al recargar y compartibles.
- **Paleta de comandos** (Ctrl/Cmd+K): New scan, Dashboard, History, Scopes, Users, saltar a run por id/ref. Accesible (rol `dialog`/`listbox`, foco gestionado).
- **Atajos:** `/` enfoca la búsqueda, `j`/`k` navegan filas, `Enter` abre, `Esc` cierra el sheet, `?` muestra la ayuda de atajos. Desactivados dentro de inputs.
- **Onboarding** de primera visita: tarjeta en el dashboard vacío que explica el gate de scope y lleva al wizard.

### 35.4 Visualización (M–L)

- **Mapa de findings GPS** en la vista de run: coordenadas parseadas del snippet con el mismo criterio que `parse_gps_line`, sin tiles de CDN (mapa vectorial base empaquetado o SVG de contorno mundial) para cumplir la CSP `connect-src 'self'`. Cada marcador abre el sheet. Cualquier dependencia nueva (p. ej. MapLibre) pasa por revisión de supply chain.
- **Tendencias de severidad** en el dashboard: requiere serie temporal en `GET /api/stats` (`buckets` por día). El cambio de API se diseña con `ui-architect` y se implementa en el backend en esta misma task.
- **Comparación de runs:** vista `/runs/compare?a=&b=` con findings nuevos / resueltos / persistentes por `dedup_signature`, reutilizando la lógica de `DeltaReporter` vía un endpoint de solo lectura.

### 35.5 Superficies de API existentes o planificadas (M)

- **Abort scan** en `run-progress.tsx` (endpoint de TASK-28) con confirmación.
- **Delete run** en History y en la vista del run (endpoint de TASK-30) con confirmación.
- **Pantalla Webhooks** (CRUD; el secreto nunca se muestra tras guardarlo) y **pantalla Knowledge** (export/import), solo para operators.

### 35.6 Deuda de arquitectura del frontend (M)

- Tipar todas las respuestas con `components["schemas"]` de `lib/api/generated/schema.d.ts`; eliminar los tipos y parsers manuales duplicados (`parseRun`, `parseFindings`, `formatWhen`).
- TanStack Query para stats, runs, findings, scopes, users y notificaciones (caché, reintentos, invalidación tras mutaciones). Zod para validar formularios (wizard, scopes, users, auth).
- Trocear `findings-panel.tsx` (~586 L) y `run-progress.tsx` (~416 L): filtros, tabla, drawer, feedback y parsers en módulos propios.
- Virtualizar la tabla de findings a partir de ~200 filas.

### 35.7 Estado de triage de findings, incluido `false_positive` (M–L)

Contrato nuevo registrado en [README.md](README.md) § Contratos compartidos: `triage_status` = `open` | `confirmed` | `false_positive` | `fixed` (default `open`). Es independiente de `severity`: marcar un falso positivo **no** cambia la severidad ni la evidencia (regla 6) y no lo decide nunca el agente, solo un operador.

- **Modelo:** columnas en `Finding`: `triage_status` (no nulo, default `open`, indexada), `triage_note` (≤500 chars, opcional), `triaged_by` (user id o `cli`), `triaged_at` (UTC). Migración Alembic + bootstrap SQLite; sin tipos exclusivos de SQLite.
- **API:** `PUT /api/runs/{run_id}/findings/{finding_id}/triage` (operator + CSRF) con `{status, note}`; filtro `?triage_status=` en el listado de findings; el campo viaja en el schema OpenAPI (regenerar `schema.d.ts`).
- **CLI (paridad):** `metatracer findings triage <finding-id> --status false_positive [--note ...]` y filtro `--triage` en `show`.
- **Reportes:** por defecto los exports excluyen `false_positive` y listan el número excluido en el resumen; `--include-false-positives` / parámetro equivalente en el API los incluye con su estado. JSON y CSV ganan la columna `triage_status`.
- **Dashboard y stats:** los conteos por severidad excluyen `false_positive`; nuevo contador "Dismissed".
- **Watch:** `DeltaReporter` no cuenta como nuevo un finding cuya `dedup_signature` fue marcada `false_positive` en un run previo del mismo scope.
- **Feedback (opcional, documentar la decisión):** marcar `false_positive` puede registrar un ejemplo de feedback para el clasificador; el `reason` libre nunca viaja al LLM (contrato TASK-13).
- **UI V2:** selector de estado en el sheet del finding con nota opcional; badge de estado en la tabla; filtro de triage (por defecto oculta `false_positive`, con toggle "Show dismissed"); acción oculta para viewers.
- **Contratos:** sincronizar `.cursor/rules/data-contracts.mdc` y la skill `metatracer-data-contracts` con el valor nuevo al implementar.

### 35.8 Light mode (M)

- **Tokens:** duplicar la paleta de `globals.css` en un tema claro (`[data-theme="light"]`) sin tocar los nombres de token; los componentes no deben usar colores literales.
- **Selección:** tres opciones "System / Dark / Light" en el shell (menú de usuario o footer del sidebar). "System" sigue `prefers-color-scheme`; la preferencia se guarda en `localStorage`. El tema se aplica antes del primer paint con un script inline compatible con la CSP (nonce o hash en `next.config.ts`, nunca `unsafe-inline` nuevo) para evitar el parpadeo.
- **Contraste:** WCAG AA (4.5:1 texto, 3:1 elementos de UI y focus ring) en ambos temas; colores de severidad recalibrados para fondo claro, siempre acompañados de su etiqueta.
- **Gráficos y mapa:** los charts SVG del dashboard y el mapa GPS (35.4) leen los tokens CSS, no colores fijos.
- **Documentación:** actualizar `v2-visual-direction.md` con la paleta clara y la decisión de producto (dark sigue siendo el default).

## 3. Fuera de alcance

- Cambios en la Web V1 (Jinja/Alpine), incluidos el triage y el light mode.
- Bulk actions sobre findings (incluido el triage masivo).

## 4. Tests mínimos

- `button` toggle: `aria-pressed=true` aplica la clase activa; filtro `Unclassified` muestra solo findings sin severity.
- Notificación con `run_id` renderiza un enlace a `/runs/{id}`.
- Viewer: no ve el drawer de feedback, Abort, Delete ni las pantallas Webhooks/Knowledge.
- Wizard: con scopes guardados seleccionados, el input manual está deshabilitado y el request solo lleva `scope_ids`.
- Modal de scope: Tab no sale del diálogo; Escape cierra y devuelve el foco.
- `AssetFindings` respeta los filtros activos y el badge abre el sheet.
- Filtros en URL: recargar restaura el mismo filtrado.
- Paleta y atajos: Ctrl+K abre, `/` enfoca la búsqueda, `j`/`k` no actúan dentro de inputs.
- Mapa GPS: snippet malformado no genera marcador ni error; contenido hostil se renderiza como texto.
- Triage: `PUT .../triage` persiste estado, nota, autor y fecha; viewer → 403; sin CSRF → 403; valor fuera del enum → 422; `severity` y `evidence_snippet` no cambian.
- Reportes: un `false_positive` no aparece en Markdown/JSON/CSV/HTML/bounty por defecto y sí con el flag de inclusión.
- Watch: una firma marcada `false_positive` no cuenta en `new_findings` del run siguiente.
- CLI: `findings triage` actualiza el estado y `show --triage open` filtra.
- Light mode: "System" sigue `prefers-color-scheme`; la preferencia persiste tras recargar; sin parpadeo de tema en el primer paint; tests de contraste AA sobre los tokens de ambos temas.
- Regresión: tests existentes de XSS, `safeUrl`, estados aborted/failed y reduced-motion siguen verdes.

## 5. Criterios de aceptación (DoD)

- [ ] El filtro activo es visible y todos los estados de severidad son filtrables.
- [ ] Notificación → run en un clic.
- [ ] Ninguna acción de mutación visible para viewers.
- [ ] Cambios sin commit de 2026-10-03 resueltos (completados o retirados).
- [ ] Filtros en URL, paleta de comandos y atajos operativos y accesibles.
- [ ] Mapa GPS, tendencias y comparación de runs sin recursos de CDN y con la CSP actual.
- [ ] Componentes tipados con el schema generado; TanStack Query + Zod en uso.
- [ ] Triage (`open`/`confirmed`/`false_positive`/`fixed`) operativo en API, CLI, Web V2, reportes, dashboard y watch, con el contrato registrado en `README.md` y sincronizado en `data-contracts.mdc`.
- [ ] Light mode con selector System/Dark/Light, AA en ambos temas y sin parpadeo.
- [ ] `npm test`, `npm run lint` y `npm run build` en `web/` verdes; suite Python verde si se toca el API.
