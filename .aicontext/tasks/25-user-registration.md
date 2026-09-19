# TASK-25 — Multi-usuario v3.1: first-run setup, panel de admin e invitaciones

**Fuente:** decisión de producto 2026-09-19 tras el análisis de estado post-TASK-24; extiende [12-platform-v3.md](../features/12-platform-v3.md) §4 (el multi-tenant se dejó a v3.1).
**Estado:** **planificada 2026-09-19**.
**Dependencias:** TASK-00 a TASK-24.

## Objetivo

Pasar de "un usuario por instalación" (TASK-24) a multi-usuario operativo **sin abrir el registro público**. Cuatro piezas:

1. **First-run setup desde la UI**: eliminar la dependencia dura de `METATRACER_AUTH_PASSWORD` sin romper el fail-closed.
2. **Panel de administración de usuarios** (solo operator): crear, cambiar rol, borrar.
3. **Invitaciones de un solo uso** generadas por operators (role = el del código, TTL, revocables).
4. **Registro desde Sign In**: enlace "Create your account" que consume un código de invitación.

Postura de producto (decisión 2026-09-19): el auto-registro abierto y la aprobación posterior de cuentas quedan fuera de alcance. **Sin invitación no se crea ninguna cuenta.** El CLI sigue sin login (postura TASK-24).

## Decisiones de diseño

- **First-run setup con token de un solo uso por consola.** Si auth está ON, la tabla `user` está vacía y NO hay `METATRACER_AUTH_PASSWORD`: la app **arranca** (cambio deliberado sobre TASK-24, que abortaba el lifespan), todas las rutas siguen 401 (no hay usuario, luego no existe sesión posible) y el arranque loguea UNA VEZ un token de setup aleatorio (`secrets.token_urlsafe(32)`) con el mensaje de crear la cuenta en `/setup`. `GET /setup` + `POST /api/auth/setup` exigen ese token. Fail-closed preservado: sin setup no hay superficie usable y sin sesión no se filtra nada.
  - Si `METATRACER_AUTH_PASSWORD` está presente → la provisión automática de TASK-24 sigue intacta (compatibilidad total) y `/setup` queda deshabilitado (404).
  - El token vive **solo en memoria** (`app.state`), se regenera en cada arranque hasta completar el setup; nunca en BD ni en respuestas API.
- **Invitaciones hasheadas** (misma técnica que las sesiones): en BD solo el SHA-256 del código; el código en claro se muestra **UNA vez** en la respuesta de creación. Un solo uso (`used_at`/`used_by`), TTL configurable (`METATRACER_INVITE_TTL_SECONDS`, default 7 días), revocable por un operator.
- **Rol del usuario nuevo = rol grabado en el código** (operator o viewer), elegido por quien lo genera. Sin aprobación posterior.
- **PBKDF2 idéntico** a TASK-24 (`hash_password`, formato versionado, mínimo 8 caracteres, verificación con dummy-hash para no revelar códigos válidos por timing).
- **Reglas de integridad del panel:** nadie se borra a sí mismo; no se puede degradar ni borrar al **último operator**; cualquier cambio de rol que deje la instalación sin operator se rechaza (409).
- **CSRF pre-sesión en `/register` y `/setup`**, igual que login (double-submit: la página emite cookie desechable que el form repite en `X-CSRF-Token`).
- **Sin enums nuevos:** `UserRole` (`operator` | `viewer`) se reutiliza tal cual; el contrato de datos no cambia.

## Alcance

### 25.1 Modelo + migración

- Modelo `InvitationCode` (`db/models.py`): tabla `invitation_code` — `id` UUID str, `code_hash` único (SHA-256 hex), `role` (`UserRole`), `created_by` FK `user`, `expires_at` (`DateTime(timezone=True)`), `used_at` nullable, `used_by` FK `user` nullable, `created_at`.
- Migración Alembic autogenerada (Postgres); SQLite la crea por `create_all` (bootstrap legacy). Las sesiones ya cascadean con el usuario (TASK-24).

### 25.2 `api/auth.py` — setup y registro

- `ensure_default_user` → nueva semántica de tres ramas: (a) password en env → provisión actual; (b) sin password y sin usuarios → token de setup en memoria + log destacado; (c) ya hay usuarios → no-op.
- `POST /api/auth/setup` `{setup_token, username, password}` → crea el primer operator; 409 si ya existe usuario; 404 si la instalación provisionó por env.
- `POST /api/auth/register` `{code, username, password}` → valida el código (no usado, no expirado), crea el usuario con el rol del código y marca el código como usado. 401 con mensaje genérico para código inválido/usado/expirado; 409 username duplicado; 422 password <8.
- Páginas `GET /register` y `GET /setup` (standalone como `login.html`, misma razón: la campana no debe hacer polling anónimo).

### 25.3 API de administración (operator only)

- `GET /api/users`, `POST /api/users` `{username, password, role}`, `PATCH /api/users/{id}` `{role}`, `DELETE /api/users/{id}` — con las reglas de integridad de arriba.
- `GET /api/invitations` (lista sin códigos: rol, estado, creada, expira, usada), `POST /api/invitations` `{role, ttl?}` (devuelve el código UNA vez), `DELETE /api/invitations/{id}` (revoca).
- Router nuevo con las dependencias de auth cableadas incondicionalmente (`get_current_user` + `require_operator_action`), igual que el resto.

### 25.4 Web UI

- `login.html`: enlace "Have an invitation code? Create your account" → `/register` (y viceversa en `register.html`: "Back to sign in").
- `setup.html`: formulario first-run (token + usuario + contraseña).
- `users.html`: panel admin — tabla de usuarios (username, rol, creado, acciones), crear usuario, cambiar rol, borrar; sección invitaciones: generar (código visible con botón copiar y aviso "won't be shown again"), listar, revocar.
- `base.html`: entrada de nav "Users" solo para operator; cabecera "Signed in as `<username>` (`<role>`)" — requiere exponer `current_user` en `_page_context` (resolviendo la sesión ya validada por el middleware).

### 25.5 Documentación y config

- `.env.example`: documentar que con auth ON la password es ahora **opcional** (si falta: flujo `/setup` con token de consola) y el TTL de invitaciones.
- `walkthrough.md` y timeline actualizados al cerrar.

## Contratos de datos

- Ningún enum nuevo ni modificado (`UserRole` reutilizado; no hay que tocar el README de contracts por enums).
- Tabla nueva `invitation_code` (migración Alembic). Los códigos se persisten **solo** hasheados; jamás en logs ni en respuestas GET.

## Seguridad (reglas inviolables — sin cambios)

- La auth sigue sin tocar pipeline, safety, webhooks ni egreso. Sin bypass, sin modo oculto.
- Fuerza bruta de códigos: acotada por el rate limit del edge y por la entropía (32 bytes urlsafe) — el código no es adivinable aunque el endpoint sea público.
- `password_hash`, `token_hash` y `code_hash` nunca aparecen en respuestas API ni en logs.

## Fuera de alcance (v3.1, deliberado)

- Auto-registro abierto sin código; cuentas pendientes de aprobación (opción descartada 2026-09-19).
- OAuth/SSO/2FA; reset de contraseña por email; equipos/workspaces compartidos.
- Comandos CLI de gestión de usuarios (se mantiene la postura CLI-sin-auth; se reevaluará si hay demanda).

## Tests

- **Unit:** `ensure_default_user` (3 ramas), reglas de integridad del panel (autoborrado, último operator), ciclo de vida del código (expira, un solo uso, revocación), hash/lookup de códigos.
- **Integración:** setup end-to-end (arranque sin password → 401 en todas las rutas → setup con token → `/setup` 409 después), register con código válido/inválido/usado/expirado/username duplicado, CRUD de usuarios + invitaciones como operator, 403 para viewer, CSRF en `/register` y `/setup`, kill-switch auth OFF = comportamiento v0.5.0 intacto.
- Suite completa verde + ruff + cobertura ≥85%.

## Criterios de aceptación

- [ ] Primera instalación con `METATRACER_AUTH_ENABLED=true` funciona **sin** `METATRACER_AUTH_PASSWORD` (setup por UI con token de consola) y sin abrir superficie sin sesión.
- [ ] Sign In enlaza al registro por invitación; sin código válido no se crea ninguna cuenta.
- [ ] Panel de usuarios operable end-to-end (crear, cambiar rol, borrar, invitar, revocar) con las reglas de integridad cubiertas por tests.
- [ ] Los códigos de invitación solo existen en claro en la respuesta de creación.
- [ ] `password_hash`/`token_hash`/`code_hash` nunca en respuestas API.
- [ ] Suite 100% verde, ruff limpio, cobertura ≥85%.
