# TASK-27: Hardening de seguridad P0 (v3.2)

**Módulo:** Safety core, webhooks, reportes, extractores, despliegue
**Referencia:** [Auditoría 2026-10-03](../audit-2026-10-03.md) § P0
**Dependencias:** TASK-00 … TASK-26
**Estado:** **Cerrada** (2026-10-03). ruff limpio; cobertura de core/detectors/extractors/reports **90.71%**. Suite completa 704 passed + 5 skipped, y el test adicional del banner de escape en verde. Revisión `safety-guardian` aprobada.

---

## 1. Objetivo técnico

Cerrar los cinco hallazgos P0 de la auditoría. Ninguno viola literalmente las reglas inviolables, pero tres de ellos (proxy, auth expuesta, XMP) permiten saltarse en la práctica las garantías que esas reglas pretenden dar.

## 2. Subtareas

### 27.1 Desactivar proxies de entorno en todo cliente HTTP

- `core/safety/http.py` (~L238) y `api/webhooks.py` (~L534): `httpx.AsyncClient(..., trust_env=False)`.
- Buscar cualquier otro `AsyncClient`/`Client` en `src/` y aplicar lo mismo.
- Motivo: con `trust_env=True` (default de httpx), `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` desvían el socket a un proxy que `NetworkSafetyGuard` nunca valida.

### 27.2 Auth obligatoria cuando el bind es público

- Al arrancar `serve` (y el entrypoint `web` del Dockerfile): si el host de bind no es loopback y `METATRACER_AUTH_ENABLED=false`, **negarse a arrancar** con un mensaje claro.
- Escape documentado: `METATRACER_ALLOW_UNAUTHENTICATED_BIND=true` (log WARNING en cada arranque). No es un bypass de safety de red: no afecta a scope ni guard. **Decisión aprobada por el operador 2026-10-03.**
- `docker-compose.yml`: `METATRACER_AUTH_ENABLED` por defecto `true`; documentar en README y `.env.example`.
- El default `false` se mantiene para `serve` en `127.0.0.1` (postura localhost-first de TASK-24).

### 27.3 Firma HMAC real en webhooks

- Decisión de diseño (**aprobada por el operador 2026-10-03**): stdlib no ofrece cifrado simétrico y la lista cerrada de dependencias no incluye `cryptography`. Se persiste el secreto en claro en `WebhookConfig` (mismo tratamiento que `headers`, que ya guardan tokens) y no se devuelve nunca por API.
- `_send`: cabeceras `X-MetaTracer-Timestamp` y `X-MetaTracer-Signature: sha256=<hex>` = `hmac.new(secret, f"{ts}.{body}", sha256)`. El body firmado debe ser exactamente el enviado (serializar una vez, `content=`).
- Migración Alembic + bootstrap SQLite: columna nueva; los configs existentes con solo `signature_secret_hash` quedan marcados como "re-introducir secreto" (sin firma hasta entonces, con warning).
- Documentar la verificación del lado receptor en README.

### 27.4 Neutralizar fórmulas en CSV

- `reports/csv_exporter.py` `_row`: toda celda de texto que empiece por `=`, `+`, `-`, `@`, `\t` o `\r` se prefija con `'`.
- Aplicar también al export bounty si se abre en hoja de cálculo (revisar `reports/bounty.py`).

### 27.5 Tope previo a la descompresión de XMP

- `extractors/pdf.py` `_xmp_fields`: no llamar a `stream.get_data()` sin límite. Leer los datos crudos (`stream._data` / `get_raw_data` según la versión de pypdf fijada) y descomprimir con `zlib.decompressobj().decompress(raw, MAX_XMP_PACKET_BYTES + 1)`; si queda `unconsumed_tail` o se supera el tope, descartar el XMP con warning (el resto de `pdfinfo` se conserva).
- Filtros distintos de FlateDecode o cadenas de filtros: descartar XMP (conservador).

## 3. Fuera de alcance

- DNS rebinding / pin de IP en el transporte (deuda aceptada O2).
- Cifrado en reposo de secretos (requiere aprobación de supply chain).
- Cambiar el default de auth para `serve` en loopback.

## 4. Tests mínimos

- Con `HTTPS_PROXY=http://127.0.0.1:9` en el entorno, `safe_httpx_request` no contacta el proxy (monkeypatch del transporte o servidor que falle si recibe conexión).
- `serve` con bind `0.0.0.0` y auth off → error de arranque; con el escape → arranca y loguea WARNING; con bind loopback → arranca.
- Webhook: la firma recibida por un receptor fake coincide con el HMAC recalculado; sin secreto no hay cabecera.
- CSV: celdas `=1+1`, `@SUM(A1)`, `-2+3`, `+cmd` salen con `'` inicial; texto normal intacto.
- PDF sintético con XMP Flate que infla a >`MAX_XMP_PACKET_BYTES`: el asset termina `ok` con campos `pdfinfo` y sin XMP; memoria acotada.

## 5. Criterios de aceptación (DoD)

- [x] Ningún cliente httpx de `src/` respeta variables de proxy.
- [x] Imposible exponer la API sin auth en un bind no-loopback sin opt-in explícito y ruidoso.
- [x] Webhooks con secreto envían firma HMAC verificable.
- [x] CSV sin inyección de fórmulas.
- [x] XMP limitado antes de inflar.
- [x] Revisión de `safety-guardian` aprobada; suite verde + ruff limpio + cobertura ≥85%.
