# Fase 14 — paridad

**Fecha:** 2026-09-29
**Estado:** Cerrada como recorrido. Ninguna fila de pantalla V1 está en `missing`. Setup queda en `in_progress`. El corte sigue fuera: falta el Playwright contra Uvicorn y el 404 HTML de setup.

`verified` en esta fase significa que el comportamiento está en el código de `web/` y coincide con la plantilla V1, más los tests de componente que ya existen. No significa que el Test de la columna (casi siempre Playwright contra el API) se haya ejecutado. Ese hueco sigue escrito en [phase-12-tests.md](phase-12-tests.md).

## Qué se comparó

Shell, aviso ético (el mismo texto en inglés), campana, sign out con CSRF, wizard y modal, `reasoning_depth` cerrado, textos 403/404/409/429 del alta, redirect con `run_id` codificado, siete etapas SSE, polling a 2 s sin marcar `failed` por un corte de socket, `aborted` distinto de `failed` según el GET, asset issues con `safeUrl`, findings en el orden del API, evidencia y prosa como texto, feedback por `apiFetch`, cinco exports, dashboard con los mismos campos que `dashboard.html` (incluidas las barras de severidad con unclassified y el uso del agente), historial con `aborted` y cursores de 50, scopes, import con el cuerpo crudo del fichero, login, register, users, viewer (el enlace Users se oculta; el 403 del API se pinta) y auth apagada (solo un 401 manda a login). Health no tiene página y el proxy no lo llama.

CLI, watch, knowledge, webhooks, pipeline y lo que V1 documenta y no tiene pantalla siguen en `out_of_scope`.

## Cambios de esta fase

- `/v2/register` responde 404 de Next cuando `GET /api/auth/me` devuelve `authenticated: false`. Con auth encendida ese GET es 401 y el formulario se muestra. Si el API no responde, el formulario sigue y el POST falla cerrado.
- La leyenda de la tabla de findings decía “ordered by severity”. El filtro no reordena. La leyenda pasa a “in API order”.

## Huecos que no son `missing`

- **Setup** (`in_progress`). El formulario y el POST existen, y el token no está en el bundle. V1 responde 404 en el HTML cuando auth está apagada, hay password de entorno, o el setup ya se consumió. No hay un GET que exponga eso sin un endpoint nuevo. No se añade. El POST del servidor sigue siendo el 404.
- **Users.** Un 409 (último operator, o borrar la propia cuenta) se muestra como `Could not delete the user (HTTP 409)`. V1 nombra el caso. La operación existe.
- **Tests de la columna.** Siguen sin hacerse el recorrido de navegador contra Uvicorn, el rol viewer en Playwright, el 202, un stream real y el fixture de safety-abort. No convierten ninguna fila en `missing`. Sí impiden tratar la matriz como ejercida de punta a punta.

## Corte

No. La fase 15 puede describir la convivencia. Mover `/` a Next sigue exigiendo otro ADR, esta matriz sin filas `missing`, el setup cerrado o aceptado por escrito, y el guardian sin bloqueantes (fase 13 ya lo está).
