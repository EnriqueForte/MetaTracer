# Fase 11 — resto de paridad

**Fecha:** 2026-09-29
**Estado:** Cerrada. Knowledge, webhooks y watch siguen fuera.

Pantallas de `web/`:

- Dashboard: solo los campos que ya pinta V1 (`runs`, `findings`, `assets`, severidad, tipos, dominios, evidencia repetida, uso del agente). Vacío si `runs.total === 0`.
- Historial: filtro de estado, contador global y cursores Newer / Older (`limit=50`).
- Scopes: alta, edición, borrado e importación del JSON portable. El fichero se reenvía tal cual.
- Login, registro y setup. El código de invitación, en Usuarios, se muestra una vez como texto y se puede descartar.
- Usuarios: crear, cambiar rol, borrar. Invitaciones: crear y revocar.

Cambio necesario en FastAPI: `GET /api/auth/me` emite la cookie CSRF previa a la sesión cuando falta. La página HTML de V1 ya no es quien la entrega al navegador de Web V2. El POST de login sin cabecera sigue siendo 403. Test: `test_me_issues_pre_session_csrf_when_cookie_missing`.
