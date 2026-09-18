# TASK-24 — Plataforma v3.0, Eje C: Auth básica (1 usuario)

**Fuente:** [12-platform-v3.md](../features/12-platform-v3.md) (sección 4)
**Estado:** **implementada, cerrada y validada en navegador 2026-09-18** (v0.5.1; security review PASS).
**Dependencias:** TASK-00 a TASK-23.

## Validación en navegador (2026-09-18, stack Docker con auth ON)

Verificado end-to-end contra la imagen `metatracer:0.5.1`: redirect de páginas
protegidas a `/login`, error con credenciales incorrectas, login correcto con
acceso completo, y **Sign out** funcional (cierra sesión server-side y redirige
a `/login`; navegar a `/` tras logout rebotará al login).

Fixes aplicados durante la validación (incluidos en el commit de cierre):

- `base.html`: `logout()` movido de la función Alpine `notifications_bell` a
  `window.MetaTracerUI`, y el botón usa `onclick` nativo. El botón vive fuera
  del scope `x-data` de la campana, así que Alpine nunca evaluaba su
  `@click` (el click no hacía nada — visto en vivo).
- `base.html`: botón Sign out condicionado a `auth_enabled and csrf_token`
  (solo se muestra con sesión activa).
- `base.html`: `authFetch` no redirige a `/login` cuando ya se está en
  `/login` (evita el bucle 401 → bell → 401 observado en vivo).
- `login.html`: página standalone (no extiende `base.html`) para que la
  campana de notificaciones no haga polling anónimo en el login.

## Resultado (2026-09-18)

- `api/auth.py`: `hash_password`/`verify_password` (PBKDF2-HMAC-SHA256 600k,
  formato `pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>`), `get_current_user`
  (401 sin sesión válida), `require_operator_action` (CSRF en métodos unsafe
  + rol operator en mutaciones; safe methods permiten cualquier usuario
  autenticado), `ensure_default_user` (provisiona el operador en el lifespan,
  fail-closed sin password o con password <8 chars), endpoints
  `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.
- `db/models.py`: `User`, `UserSession`, enum `UserRole`.
- Migración Alembic `77f92328cc8e` (validada contra `pgvector/pgvector:pg17`
  real: upgrade desde cero, idempotencia, ORM roundtrip).
- Wiring incondicional: los routers de datos llevan siempre las dependencias;
  con auth OFF (default) son no-op y el comportamiento es exactamente v0.5.0.
- Middleware: páginas HTML redirigen a `/login` (307) sin sesión; `/login`,
  `/api/health`, `/static/*` y `/api/auth/*` exentos.
- Web UI: `login.html`, botón "Sign out" en `base.html`, helper `authFetch`
  que añade `X-CSRF-Token` (token leído de `<meta name="csrf-token">`) y
  redirige a `/login` en 401; todos los fetch mutantes de los templates
  pasan por él.
- Tests: 31 nuevos (`tests/unit/test_auth.py`,
  `tests/integration/test_api_auth.py`). Suite: 603 passed, ruff limpio,
  cobertura 86.9% (≥85%).
- **Security review (safety-guardian, 2 pasadas):** la primera dio FAIL con
  un HIGH real — el CRUD de webhooks (`register_routes` con
  `add_api_route`) no llevaba las dependencias de auth. Corregido: las 5
  rutas `/api/webhooks*` van con `get_current_user` +
  `require_operator_action`. También corregidos: login-CSRF (double-submit
  pre-sesión: `GET /login` emite cookie CSRF desechable que el form repite
  en el header), logout-CSRF, FK `user_session.user_id` con
  `ondelete=CASCADE` (migración), fetch de notificaciones vía `authFetch`.
  Segunda pasada: **PASS**, 7/7 reglas inviolables OK.

## Objetivo

Convertir MetaTracer en una plataforma que puede exponerse en red: la seguridad
deja de depender solo del bind address. Una sesión por cookie `HttpOnly` con
CSRF y roles `operator`/`viewer` protegen la superficie Web/API. **El CLI sigue
sin login** (localhost, un solo operador — postura documentada en la feature).

## Decisiones de diseño (revisión supply-chain 2026-09-18)

- **Hash de contraseñas: stdlib.** `hashlib.pbkdf2_hmac("sha256", ...)` con
  600.000 iteraciones + `hmac.compare_digest` (comparación constante).
  **Cero dependencias nuevas** (descarta `bcrypt`/`argon2-cffi`/`passlib`:
  código nativo que no aporta nada real para 1 usuario operador; passlib está
  en mantenimiento con incompatibilidades conocidas de bcrypt>=4.1). OWASP
  sigue listando PBKDF2-HMAC-SHA256 600k como opción aceptable.
- **Formato almacenado:** `pbkdf2_sha256$600000$<salt_b64>$<hash_b64>` —
  auto-descriptivo y versionado (permite subir iteraciones con
  rehash-on-login sin migración).
- **Sesión:** token aleatorio `secrets.token_urlsafe(32)`; en BD se guarda
  **SHA-256** del token (leak de la BD no da sesiones válidas). Cookie
  `HttpOnly; SameSite=Lax; Path=/`; flag `Secure` cuando el request no es
  localhost/HTTP explícito. Expiración en BD (`expires_at`) verificada en
  `get_current_user`, no solo en la cookie. **Rotación en cada login**
  (anti-fixation: el token nuevo invalida el anterior).
- **CSRF:** double-submit cookie (`csrf_token` cookie no-HttpOnly aleatoria e
  independiente + header `X-CSRF-Token` en cada mutación unsafe; comparación
  con `compare_digest`). Solo aplicado a métodos no-safe (POST/PUT/PATCH/
  DELETE) de rutas bajo auth.
- **Roles:** `operator` (todo) y `viewer` (solo lectura: GET). Los endpoints
  mutantes exigen `operator`; los GET, cualquiera autenticado.

## Alcance

### 24.1 Modelo + migración

- Modelo `User` (`db/models.py`): tabla `user` — `id` UUID, `username` único,
  `password_hash`, `role` (StrEnum `UserRole`: `operator` | `viewer`),
  `created_at`. **Un usuario por instalación en v3.0** (más filas quedan para
  v3.1).
- Modelo `UserSession` (`db/models.py`): tabla `user_session` — `id` UUID,
  `user_id` FK, `token_hash` único (SHA-256 hex del token), `expires_at`
  (`DateTime(timezone=True)`), `created_at`. Sesiones: artefacto de seguridad,
  nunca fuente de datos de negocio.
- Migración Alembic autogenerada (Postgres); SQLite lo crea por
  `create_all` (bootstrap legacy).

### 24.2 Módulo `api/auth.py`

- `hash_password(password) -> str` / `verify_password(password, stored) -> bool`.
- `login(username, password) -> (session_token, csrf_token)` — verificación
  con `compare_digest`; **latencia constante aproximada**: si el usuario no
  existe se verifica contra un hash dummy para no revelar existencia por
  timing. Rate limit del edge ya acota brute force (120 req/min/IP).
- `get_current_user(request) -> CurrentUser` — dependencia FastAPI: lee
  cookie, hashea, busca sesión en BD, valida `expires_at`, devuelve
  `CurrentUser(id, username, role)`. 401 si no hay sesión válida.
- `require_operator(user)` — dependencia que sube a 403 si el rol no es
  `operator`.
- `require_csrf(request, user)` — compara header vs cookie para métodos
  unsafe. 403 si no coincide.
- `ensure_default_user(session_factory, settings)` — en el lifespan: si no
  existe ningún usuario, crea el operador inicial con la contraseña de
  `METATRACER_AUTH_PASSWORD` (obligatoria solo cuando `auth_enabled=True`;
  si falta y auth está activo → el lifespan falla con mensaje claro). Sin
  password en logs, nunca.
- **Kill-switch:** `METATRACER_AUTH_ENABLED` (default `false` en v0.6.0) —
  permite desplegar en localhost sin login como hoy. Cuando `true`, TODOS los
  endpoints (menos `/api/health`, `/static/*` y la propia login page) exigen
  sesión. El default flip a `true` es una decisión futura de release, no de
  esta task.

### 24.3 Endpoints

- `GET /login` — página de login (template mínimo, mismo base.html).
- `POST /api/auth/login` — JSON `{username, password}`; fija cookies
  (`metatracer_session`, `csrf_token`); 401 en credenciales inválidas.
- `POST /api/auth/logout` — borra la sesión de BD y expira cookies (csrf en
  la propia llamada: el usuario ya está autenticado).
- `GET /api/auth/me` — diagnóstico: usuario y rol actual.
- Existentes: con auth activo, todas las rutas JSON y páginas ganan
  `Depends(get_current_user)` vía **router dependency** (no editando cada
  handler: se aplica al include_router en `app.py`). Los mutantes añaden
  `require_operator` + CSRF. `/api/health`, `/static/*` y `GET /login`
  quedan exentos.

### 24.4 Web UI

- `login.html`: formulario mínimo (username/password), estilo del sistema.
- `base.html`: enlace "Sign out" cuando hay sesión; el CSRF token se inyecta
  como `<meta name="csrf-token">` y el JS compartido lo lee para los fetch
  mutantes (si algún fetch existente no lo manda → 403 con mensaje claro).
- Logout con `POST /api/auth/logout` (nunca GET).

## Contratos de datos

- Nuevo enum cerrado `UserRole`: `operator` | `viewer` (minúsculas en BD/JSON,
  como el resto). Registrado en el README de contracts si se añade algo —
  este enum es nuevo, hay que añadirlo a `.aicontext/tasks/README.md` y al
  skill data-contracts.
- Sin cambios en enums/severity/dedup existentes. La tabla `user` de una fila
  no cambia el ciclo de vida de findings/runs.

## Seguridad (reglas inviolables — sin cambios)

- La auth **no toca** el pipeline, ni el safety, ni webhooks/dispatcher: solo
  quién puede llamar a los endpoints. Las 7 reglas quedan idénticas.
- El payload de webhook sigue sanitizado y fijo (`PAYLOAD_KEYS`); la auth es
  una capa más sobre ese egreso, no un cambio de contrato.
- `METATRACER_ALLOW_LOOPBACK` sigue siendo solo-test y ajeno a la auth.
- Nunca loguear la contraseña ni el token de sesión; `password_hash` no se
  expone en ninguna respuesta API (ni siquiera `me`).

## Fuera de alcance (v3.0, deliberado)

- OAuth/SSO/2FA, multi-tenant (N usuarios), reset de contraseña por email.
- Auth en el CLI (localhost) y en el webhook dispatcher (egreso con secrets
  propios, no superficie de entrada).
- HTTPS terminación/reverse proxy (documentación de despliegue, no código).

## Tests

- **Unit** (`tests/unit/test_auth.py`): hash/verify (roundtrip, contraseña
  errática, formato versionado, rehash), latencia constante del login miss,
  token hash estable, expiración, roles.
- **Integración** (`tests/integration/test_api_auth.py`): con
  `auth_enabled=True` — 401 sin cookie, 401 con sesión expirada, 403 CSRF
  ausente/incorrecto en mutaciones, 403 viewer en mutaciones, viewer puede
  GET, operator puede todo, login/logout/me flujos completos, kill-switch
  `auth_enabled=False` permite todo como v0.5.0.
- **Suite completa** + ruff + cobertura ≥85% (los 4 paquetes del DoD).

## Criterios de aceptación

- [ ] Con `METATRACER_AUTH_ENABLED=true`, ningún endpoint de datos responde
      sin sesión válida (comprobado por tests de integración).
- [ ] CSRF en todas las mutaciones unsafe (403 sin header/mismatch).
- [ ] `viewer` no puede crear scopes/webhooks ni lanzar scans (403); sí lee.
- [ ] Login rota el token de sesión; logout invalida en BD.
- [ ] `password_hash` y `token_hash` nunca aparecen en respuestas API.
- [ ] Con `auth_enabled=False` (default), el comportamiento es idéntico a
      v0.5.0 (localhost sin login) — cero breaking change.
- [ ] Suite 100% verde, ruff limpio, cobertura ≥85%.
