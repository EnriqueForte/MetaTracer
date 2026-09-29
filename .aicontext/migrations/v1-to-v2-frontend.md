# Plan de migración Web V1 → Web V2

Estado: ADR aceptado el 2026-09-26. Fases 0 a 15 cerradas en el programa de convivencia. `/` sigue en FastAPI. `/v2` se compara con `npm run coexist` en `web/`, sin corte. Setup sigue en `in_progress`. El Playwright contra Uvicorn sigue abierto. El corte de `/` exige otro ADR.

Decisiones que este plan obedece: [ADR-001](../architecture/ADR-001-nextjs-react-migration.md). Contrato: [api-contract-v1.md](../architecture/api-contract-v1.md). Forma del cliente: [v2-frontend-architecture.md](../architecture/v2-frontend-architecture.md). Dirección visual: [v2-visual-direction.md](../architecture/v2-visual-direction.md). Trazabilidad: [feature-parity-matrix.md](feature-parity-matrix.md).

## Principio

V1 (FastAPI + Jinja + Alpine + CLI) sigue siendo el producto que arranca por defecto. V2 es un paquete `web/` servido en `/v2` del mismo origen. El API no se versiona: no hay `/api/v2`.

Nada de este plan modifica extractors, detectors, agentes LLM, SQLite, CLI ni `ScanOrchestratorService`, salvo que un checkpoint demuestre que un bug de contrato impide consumir el API. En ese caso se para y se escribe el problema; no se “aprovecha” el frontend para cambiar el backend.

## Fases

### Fase 0 — Descubrimiento

Hecho al escribir estos documentos. Incluye discrepancias doc/código, inventario de rutas, SSE, agentes y la conclusión de que el backend no necesita cambios para un cliente same-origin.

**Salida:** ADR redactado.
**Checkpoint:** cerrado. El ADR pasó a Aceptada en la fase 1.

### Fase 1 — Decisión

Cerrada el 2026-09-26. El ADR quedó **Aceptada**. No se crearon archivos de agente. El índice de `decisions/` apunta al ADR. La dirección visual de las fases de UI está en `v2-visual-direction.md`.

### Fase 2 — Contrato ejecutable

Cerrada el 2026-09-26. Nota: [phase-2-contract-spike.md](../architecture/phase-2-contract-spike.md). Tipos en `spikes/web-v2-contract/schema.d.ts`, generados con `openapi-typescript` 7.13.0. `src/metatracer/` no cambió.

Los modelos con nombre (scan, findings, scopes, usuarios, feedback, notificaciones) salen tipados. Auth, dashboard anidado, SSE y respuestas de webhooks quedan abiertos en el schema. No se corrigió en Python: es un cambio de contrato aparte, y las pantallas que los lean no pueden tratar el tipo generado como cerrado.

### Fase 3 — Fundación

Cerrada el 2026-09-26. Nota: [phase-3-foundation.md](../architecture/phase-3-foundation.md).

`web/` con Next 16.3.6, React 19.3.0 y TypeScript 5.9.3. `basePath` `/v2`. Rewrite de `/api` al FastAPI. CSP de producción sin `unsafe-eval` y sin orígenes de terceros; `'unsafe-inline'` se queda por los scripts de hidratación de Next. `pyproject.toml` no cambió.

### Fase 4 — Primitivas y tokens

Cerrada el 2026-09-29. Nota: [phase-4-primitives.md](../architecture/phase-4-primitives.md).

Tokens `--mt-*` portados sin cambiar la escala de severidad. Primitivas en `web/src/components/ui/`. Tailwind 4 solo dentro de `web/`. Sin páginas de dominio.

### Fase 5 — Shell

Cerrada el 2026-09-29. Nota: [phase-5-shell.md](../architecture/phase-5-shell.md).

Nav, aviso ético, campana y sign out. Las pantallas enlazadas aún no tienen datos. Auth shells sin campana.

### Fase 6 — Wizard y scope

Cerrada el 2026-09-29. Nota: [phase-6-wizard.md](../architecture/phase-6-wizard.md).

Modal bloqueante, checkbox desmarcado, una sola fuente de scope en el POST, 202 hacia `/runs/{id}`. El progreso de esa página es la fase 7.

### Fase 7 — SSE

Cerrada el 2026-09-29. Nota: [phase-7-sse.md](../architecture/phase-7-sse.md).

Stream same-origin, polling de respaldo, `aborted` y `failed` según el GET. Sin cancelación. Los findings son la fase 8.

### Fase 8 — Findings

Cerrada el 2026-09-29. Nota: [phase-8-findings.md](../architecture/phase-8-findings.md).

Tabla, filtros, evidencia como texto, `safeUrl` y `severity` null como Unclassified. La prosa del modelo es la fase 9.

### Fase 9 — Análisis del modelo

Cerrada el 2026-09-29. Nota: [phase-9-analysis.md](../architecture/phase-9-analysis.md).

Justificación, impacto, remediación y pasos como texto. Feedback por corrección de severidad (`up` / `down`). Las descargas son la fase 10.

### Fase 10 — Reportes

Cerrada el 2026-09-29. Nota: [phase-10-reports.md](../architecture/phase-10-reports.md).

Cinco descargas (`md`, `json`, `html`, `csv`, `bounty`) con el `run_id` codificado. El resto de paridad es la fase 11.

### Fase 11 — Resto de paridad

Cerrada el 2026-09-29. Nota: [phase-11-parity.md](../architecture/phase-11-parity.md).

Dashboard, historial con cursor, scopes, login, registro, setup, usuarios e invitaciones. Knowledge, webhooks y watch no entran.

### Fase 12 — Tests

Cerrada el 2026-09-29 en el job `web` y en Vitest. Nota: [phase-12-tests.md](../architecture/phase-12-tests.md).

pytest de V1 (`not e2e`) en verde. Playwright de este checkpoint solo comprueba el modal de scope. El recorrido wizard → 202 → SSE contra el API real y el mock origin sigue pendiente y no se da por verificado.

### Fase 13 — Revisión de seguridad

Cerrada el 2026-09-29. Nota: [phase-13-security.md](../architecture/phase-13-security.md).

Veredicto del safety-guardian: **SIN BLOQUEANTES**. Dos avisos de CSRF en los formularios de auth quedan escritos y no abren un bypass: el servidor sigue en 403. `.dockerignore` excluye `web/` entero después de ese veredicto.

### Fase 14 — Paridad

Recorrida el 2026-09-29. Nota: [phase-14-parity.md](../architecture/phase-14-parity.md). Matriz: [feature-parity-matrix.md](feature-parity-matrix.md).

Ninguna fila de pantalla V1 está en `missing`. Setup queda en `in_progress`. `verified` es paridad leída en el código, no el Playwright contra el API.

### Fase 15 — Convivencia

Cerrada el 2026-09-29. Nota: [phase-15-coexistence.md](../architecture/phase-15-coexistence.md).

`/v2` se publica solo si se arranca el proxy opt-in. `/` sigue en FastAPI. El shell de V2 avisa de que el sign out cierra también la sesión de la UI clásica.

El corte (proxy de `/` hacia Next, V1 a `/legacy` o retirada de plantillas) **no está incluido**. Requiere otro ADR. Hasta entonces, borrar una plantilla es un incidente, no un cleanup.

## Checkpoints (todas las fases de implementación)

1. La arquitectura de la fase sigue el ADR (mismo origen, sin BFF de negocio, sin autoridad en cliente).
2. Tests de la fase, más la suite pytest relevante (`not e2e` como mínimo; e2e si se tocó un flujo de scan).
3. `/openapi.json` sin diff, o diff explicado y aceptado como cambio de contrato aparte.
4. Ojos de seguridad en el diff de `web/` (aunque el veto formal sea el de la fase 13, un `dangerouslySetInnerHTML` para la fase en seco).
5. Nota de qué cambió. `docs-architect` si la fase cerró comportamiento visible.
6. Arranque de Web V1: `GET /` y un test de página existente siguen pasando.

## Rollback

| Momento | Acción | Datos |
| :--- | :--- | :--- |
| Fases 0–2 | Borrar o ignorar documentos de spike y tipos generados | Ninguno |
| Fases 3–14 | No publicar la ruta `/v2`. El directorio `web/` puede quedarse en el repo sin estar en el proxy | Ninguno. SQLite no migra |
| Fase 15 | Parar `npm run coexist`. Uvicorn sigue sirviendo `/` | Ninguno. SQLite no migra |
| Tras un corte futuro | El proxy devuelve el documento HTML a Uvicorn. Las plantillas tienen que seguir en el árbol | Ninguno |

No hay migración Alembic asociada. No hay flag `--v2` en la CLI.

## Qué se elimina, y cuándo

Nada de V1 se elimina en este plan. Orden futuro, solo tras ADR de corte:

1. Dejar de enrutar `/` a Jinja.
2. Mantener las plantillas una release por si el rollback es volver a enrutar.
3. Retirar plantillas, Alpine y el Tailwind compilado de V1 en un cambio propio, con la matriz en `removed-after-cutover`.
4. Entonces, y no antes, se retiran o archivan `ui-engineer` y `ui-architect`, o se marcan legacy. Hacerlo durante la fase 3 dejaría Web V1 sin dueño.

## Riesgos operativos de la convivencia

- Dos Tailwind y dos juegos de CSS. Aceptado: no se comparte el `tailwind.css` compilado de V1 con el pipeline de Next.
- El operador puede tener las dos UIs abiertas. Comparten cookie de `Path=/`. Un logout en una cierra la sesión de la otra. Es lo correcto; hay que decirlo en la UI de `/v2` (“Signing out also ends the session used by the classic UI”).
- `ProgressBus` y `NotificationBus` son memoria de proceso. V1 y V2 ven el mismo stream si pegan al mismo Uvicorn. No hace falta un bus nuevo.
