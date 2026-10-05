# TASK-31: Endurecimiento de límites y autorización del API (v3.2)

**Módulo:** `api/app.py`, `core/ratelimit.py`, `api/scopes.py`, `api/knowledge.py`, `api/auth.py`, `api/users.py`
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P1-5, P1-6
**Dependencias:** TASK-27
**Estado:** **Cerrada** (2026-10-03). ruff limpio; cobertura core/detectors/extractors/reports **90.84%** (715 passed, not e2e).

`read_body_capped` y el canal `receive` paran al superar `max_request_body_bytes`, también sin `Content-Length`. Un `Content-Length` no numérico responde 400. `require_operator` cubre GET de usuarios, invitaciones, webhooks y el export de la KB. Con auth apagada esos endpoints siguen abiertos. La instalación es un único dominio de confianza: todo usuario autenticado ve todos los runs.

---

## 1. Objetivo técnico

1. El tope de body de 5 MiB solo mira `Content-Length` (`app.py` ~L182–185). Con `Transfer-Encoding: chunked`, `await request.body()` en los imports de scopes y KB carga cuerpos sin límite.
2. `require_operator_action` hace early-return en métodos de lectura, así que un viewer lee `/api/users` y `/api/invitations`. La UI oculta la sección, el API no.

## 2. Subtareas

### 31.1 Tope de body real

- Helper `read_body_capped(request, max_bytes)` que lee `request.stream()` acumulando y lanza 413 al superar el tope; usarlo en `api/scopes.py` (import) y `api/knowledge.py` (import), y en cualquier endpoint que lea `request.body()`.
- Alternativa en el middleware: envolver `receive` para contar bytes en cuerpos sin `Content-Length`.
- Rechazar `Content-Length` no numérico con 400.

### 31.2 Autorización de lectura admin

- Nueva dependencia `require_operator` (también en GET) para `users.router` e `invitations_router`.
- Revisar el resto de GETs: `knowledge` export y `webhooks` (config con cabeceras/tokens) también deben ser operator-only.
- Con auth desactivada el comportamiento no cambia (no-op).

## 3. Fuera de alcance

- Aislamiento de runs por usuario (multi-tenant). Documentar en README que la instalación es un único dominio de confianza: todo usuario autenticado ve todos los runs.

## 4. Tests mínimos

- POST chunked de 6 MiB a `/api/scopes/import` y `/api/knowledge/import` → 413 sin cargar el cuerpo entero.
- Viewer: `GET /api/users`, `GET /api/invitations`, `GET` de webhooks y export KB → 403; operator → 200.
- Auth desactivada: los mismos endpoints responden 200 (regresión).

## 5. Criterios de aceptación (DoD)

- [x] Ningún endpoint lee más de `max_request_body_bytes` con o sin `Content-Length`.
- [x] Los viewers no acceden a datos de administración ni a secretos de integraciones.
- [x] Suite verde + ruff limpio + cobertura ≥85%.
