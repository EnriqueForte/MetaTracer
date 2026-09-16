# Revisión de seguridad — veredicto safety-guardian (2026-09-16)

**Proyecto:** MetaTracer
**Ámbito:** auditoría completa (auditoría de repo 2026-09-16) — core/, extractors/, detectors/, classification/, agents/, api/, services/, pyproject.toml, .env.example, Dockerfile, compose, CI
**Método:** revisión estática del código contra las [7 reglas inviolables](README.md) y el modelo de amenazas. No se ejecutó código.
**Veredicto:** ✅ **PASS CON OBSERVACIONES** — sin hallazgos críticos, sin violaciones de reglas inviolables.

## Veredicto por regla

| Regla | Estado |
| :--- | :--- |
| 1. Red con `scope_confirmed` + ScopeValidator + Guard | ✅ Conforme (`core/safety/http.py` kwargs obligatorios; webhook egress = excepción documentada con anti-SSRF propio) |
| 2. Sin modo oculto | ✅ Conforme (sin `--insecure`; solo shortcut documentado de confirmación en UI) |
| 3. Cero binarios | ✅ Conforme (bodies solo en memoria/temp; `sanitize_value` rechaza blobs; payload LLM cerrado por esquema) |
| 4. Redirects in-scope | ✅ Conforme (max 5 hops, re-valida cada hop antes de leer body) |
| 5. Asset fallido no tumba run | ✅ Conforme (triple capa: ingest por-asset, registry, orquestador `_fail`) |
| 6. Agentes no inventan | ✅ Conforme (esquema sin `finding_type`/`evidence_snippet`; guard post-LLM solo baja/rechaza) |
| 7. Loopback/privadas bloqueadas | ✅ Conforme (guard con desmapeo IPv4-mapped; `allow_loopback` solo en tests y CI en proceso) |

## Deuda aceptada / observaciones (sin riesgo actual)

- **O1** `core/config.py:37`: `METATRACER_ALLOW_LOOPBACK=true` es activable por env en cualquier despliegue (guardrail documental, se refuerza con R1).
- **O2** TOCTOU/DNS rebinding: limitación aceptada del MVP, documentada en `guard.py`; mitigación (guard inmediato por request/hop) se cumple.
- **O3** Body cap de 5 MiB sin excepción por endpoint (seguro, solo rígido para imports futuros).
- **O4** `WebhookDelivery.payload_json`: caché de retries en disco (solo claves fijas + summary cap 300; sin secretos de cabecera).
- **O5** `--reload` + bind 0.0.0.0 sin rate limiter: defensa en profundidad, no violación.

## Recomendaciones priorizadas (portafolio)

**P1 (próximo slice):**
- **R1** `get_settings()`: warning fuerte si `allow_loopback=True` y no hay marcador de tests (p. ej. `PYTEST_CURRENT_TEST`). Sin dependencias nuevas.
- **R2** Test de que el middleware de borde no rompe SSE bajo carga del mismo cliente (scan + polling + stats en la misma ventana no debe 429).
- **R3** `_head_probe` consume 2 slots de rate limit por asset (HEAD+GET). Documentar el coste o sustituir por probe barato.
- **R4** Redactar `config.headers` (pueden contener tokens) ante cualquier log de httpx en el cliente de webhooks.

**P2 (higiene):**
- **R5** Unificar normalización NFC en `classification/anchor.py` (hoy falso-negativo conservador).
- **R6** Test explícito de `sanitize_for_log` con ANSI.
- **R7** `engine.dispose()` + logout ordenado en shutdown.
- **R8** Documentar el coste de `_head_probe` en README si no se cambia.

## Fuentes de verdad consultadas
- `.cursor/rules/safety-invariants.mdc`
- `.cursor/rules/data-contracts.mdc`
- `.aicontext/tasks/README.md` (§ Reglas inviolables)
- `.aicontext/tasks/00-architecture-and-safety.md` (layout v2.3)

**Estado:** veredicto emitido; P0 = ninguno. Re-auditar tras cualquier cambio en core/, agents/, api/, pyproject.toml o .env.example (regla de proyecto).