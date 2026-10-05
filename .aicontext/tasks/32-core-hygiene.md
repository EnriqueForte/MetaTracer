# TASK-32: Higiene del safety core y de la cadena de suministro (v3.2)

**Módulo:** `core/config.py`, `core/safety/{guard,scope,http}.py`, `core/ratelimit.py`, `extractors/`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P2 (safety core y supply chain); recomendaciones R1, R3, R8 de la [revisión 2026-09-16](../security-review-2026-09-16.md)
**Dependencias:** TASK-27
**Estado:** **Cerrada** (2026-10-05). Revisión safety-guardian APROBADO.

---

## 1. Objetivo técnico

Cerrar la deuda P2 del perímetro de red y extracción, y hacer reproducibles los builds.

## 2. Subtareas

### 32.1 Kill-switch de `METATRACER_ALLOW_LOOPBACK` (R1)

- `get_settings()`: si `allow_loopback=True` y no hay `PYTEST_CURRENT_TEST`, log ERROR y negarse a arrancar `serve`/`scan`/`watch`. El servidor mock de tests sigue funcionando.

### 32.2 Rangos IP adicionales

- Añadir a `_OTHER_BLOCKED_NETWORKS`: `0.0.0.0/8`, `192.0.0.0/24`, `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `198.18.0.0/15`, `240.0.0.0/4`, `255.255.255.255/32`, `2001:db8::/32`, `100::/64`.
- Rechazar antes de DNS los hosts con forma de IPv4 no canónica (decimal `2130706433`, octal `0177.0.0.1`, hex).

### 32.3 Normalización IDN única

- `normalize_host` convierte a punycode (`encode("idna")`) igual que `urlsplit().hostname` en el transporte. Scope y URL se comparan en la misma forma.
- Rechazar en la creación de scopes las bases de una sola etiqueta (`com`, `*.com`) y avisar de sufijos públicos conocidos (`co.uk`).

### 32.4 Rate limiting

- `ApiRateLimiter.check`: calcular el resultado dentro del lock y lanzar el 429 fuera; eliminar el `await asyncio.sleep(0)` bajo lock y el comentario incorrecto.
- Tras un HEAD con redirects, hacer el GET sobre la URL final validada (no recorrer otra vez la cadena). Documentar el coste residual HEAD+GET en README (R3/R8).

### 32.5 Robustez de extractores

- `extractors/javascript.py`: tope de profundidad (p. ej. 64) en `_skip_string` ↔ `_skip_template_expr`, o versión iterativa.
- `extractors/image.py`: fijar `Image.MAX_IMAGE_PIXELS` explícitamente al importar.
- `extractors/crawler.py`: Content-Type vacío → sniff de `<!doctype`/`<html` antes de parsear.
- Al arrancar, borrar temporales `metatracer-*` huérfanos más antiguos de 1 h.

### 32.6 Cadena de suministro

- Mover `piexif` a `[project.optional-dependencies] dev`.
- Lockfile con hashes (`requirements.lock` generado con `pip-compile --generate-hashes` o equivalente) usado en el stage builder del Dockerfile.
- Alinear el tag de imagen en `docker-compose.yml` con la versión del paquete.
- Profile `postgres`: sin default para `POSTGRES_PASSWORD` (fallar si no está definida).

## 3. Fuera de alcance

- Pin de IP en el transporte contra DNS rebinding (deuda aceptada).
- Bloqueo de NAT64/6to4/Teredo.

## 4. Tests mínimos

- `allow_loopback=True` fuera de pytest → error de arranque (simulando ausencia de `PYTEST_CURRENT_TEST`).
- Guard bloquea cada rango nuevo y las formas decimal/octal/hex de 127.0.0.1.
- Scope `münchen.de` coincide con URL `xn--mnchen-3ya.de` y viceversa; `*.com` rechazado.
- Rate limiter: dos peticiones concurrentes no se serializan por el lock (test con tiempos).
- JS con 10 000 `${` anidados → asset `ok` o `failed` sin `RecursionError` ni bloqueo.
- Imagen que supera `MAX_IMAGE_PIXELS` → `failed` con `error_message`.

## 5. Criterios de aceptación (DoD)

- [x] El bypass de loopback es inutilizable fuera de la suite.
- [x] Guard alineado con las listas SSRF habituales.
- [x] Build Docker reproducible desde un lockfile con hashes; `piexif` fuera de runtime.
- [x] Revisión de `safety-guardian`; suite verde + ruff limpio + cobertura ≥85%.
