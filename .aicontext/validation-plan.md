# Plan de validación en entorno real (Fase 0 post-MVP)

**Proyecto:** MetaTracer
**Estado:** Cerrado — 2026-09-06. MVP v1.0 validado; v1.1 y v1.2 cerradas ([roadmap](features/10-timeline-and-roadmap.md))
**Relación:** verificó los [criterios de éxito](features/09-success-criteria.md) fuera de la suite de tests

El MVP está verde en fixtures sintéticos y loopback. Esta fase demuestra que la herramienta cumple sus tres criterios de éxito **contra la realidad**, y genera el histórico de métricas que gobierna el ajuste de detectores, rúbrica y prompts.

## Principio inviolable

Solo targets autorizados, según [ética y safety](features/08-ethics-legal-safety.md): assets propios, auditorías con permiso explícito o programas de bug bounty in-scope. Ninguna etapa de este plan requiere `METATRACER_ALLOW_LOOPBACK` (eso es solo para la suite de tests) ni desactivar ningún control de safety.

## Qué se mide

| Métrica | Definición | Umbral |
| :--- | :--- | :--- |
| Precisión por tipo | TP / (TP + FP) del detector | 1.0 en sitio sembrado; ≥ 0.9 en real |
| Recall por tipo | TP / (TP + FN) del detector | 1.0 en sitio sembrado; ≥ 0.9 en real |
| Falsos positivos | Findings sin expectativa que los respalde | 0 en sitio sembrado; cada uno triageado en real |
| Calibración de severidad | % de TP con `severity` == `expected_severity` | ≥ 80% tras rellenar el ground truth |
| `unclassified` en reporte | Findings con `severity` NULL en el JSON exportado | 0 (el clasificador siempre corre) |
| Evidencia | El snippet contiene los substrings esperados | 100% en sitio sembrado |

Herramienta: `validation/measure.py` (offline, compara el JSON exportado con un ground truth). Registro histórico: `--json-out validation/results/<fecha>-<target>.json`.

## Etapa 0.1 — Sitio sembrado propio (ground truth total)

Objetivo: precisión y recall **perfectos** contra un target con ground truth conocido al 100%.

```powershell
# 1. Generar el sitio (fixtures sintéticos + ground_truth.json)
.venv\Scripts\python.exe -m validation.seed_site --target https://validation.tu-dominio.com

# 2. Subir validation/site/ (EXCEPTO ground_truth.json) a un dominio propio

# 3. Escanear (el orquestador exporta .md y .json a reports/ al terminar)
.venv\Scripts\python.exe -m metatracer scan https://validation.tu-dominio.com

# 4. Medir — debe salir RESULT: OK con P=1.00 R=1.00
.venv\Scripts\python.exe -m validation.measure `
  --report reports\metatracer-validation-tu-dominio-com-....json `
  --ground-truth validation\site\ground_truth.json `
  --min-precision 1.0 --min-recall 1.0 `
  --json-out validation\results\2026-09-05-seeded-site.json
```

Cualquier FP/FN aquí es un bug del pipeline, no del mundo real: se corrige antes de seguir. Después del primer scan, rellenar `expected_severity` en el ground truth con el criterio humano (ese ejercicio **es** la calibración) y volver a medir.

## Etapa 0.2 — Dominio propio real (triage manual)

Objetivo: medir falsos positivos contra metadata real no controlada (cámaras reales, Office real, CDNs que reescriben cabeceras, etc.).

1. Escanear un dominio propio con documentos reales publicados.
2. Triagear **cada** finding del reporte: ¿la evidencia es real? ¿la severidad es la que tú pondrías? ¿la explicación inventa algo?
3. Volcar el triage en un ground truth manual con `complete: false` mientras queden assets sin revisar; pasar a `complete: true` cuando el triage cubra todo el sitio.
4. Re-medir y guardar el registro en `validation/results/`.

## Etapa 0.3 — Programa de bug bounty in-scope

Objetivo: validar el criterio #2 (reporte enviable) en condiciones reales.

1. Elegir un programa cuyo scope permita explícitamente recon automatizado sobre documentos públicos; respetar su rate limit (el default conservador de MetaTracer no se toca).
2. Escanear, triagear manualmente todo (ground truth con `complete: false`).
3. Si hay hallazgos reales y el reporte cumple el estándar de envío: enviarlo al programa. Un reporte aceptado es la evidencia más fuerte del criterio #2.
4. **No commitear** ground truths ni resultados de terceros: `validation/results/` está fuera de git y los ground truths reales se guardan locales.

### Programas evaluados (2026-09-06, políticas leídas en HackerOne)

| Criterio | Reddit | DoD (VDP) |
| :--- | :--- | :--- |
| Metadata/EXIF excluido explícitamente | No | No |
| Exclusión que SÍ nos afecta | "Component version disclosure without accompanying proof of vulnerability" → `software_version` solo no es reportable ahí | "High-volume of low-quality reports" prohibido → un solo target, triage manual |
| Safe harbor | Gold Standard | Protección legal (no Gold Standard) |
| Scope | `*.reddit.com`, `*.snooguts.net` (27 assets) | Cualquier sistema público del DoD (scope abierto) |
| Bounty | $250–$15.000 (Low: $250–500) | No (VDP, reconocimiento público) |
| Precedente | [#1069039](https://hackerone.com/reports/1069039): GPS en HEIF→PNG aceptado y corregido | 31.689 reportes resueltos |

**Estrategia**: DoD primero (scope abierto, acepta informativos, enorme superficie de PDFs públicos en `.mil` — máxima probabilidad de reporte aceptado). Reddit solo si encontramos GPS/email/path (version disclosure simple está excluido). Requisito previo: cuenta en HackerOne + LLM configurado para la prosa del reporte.

## Loop de mejora

Cada falso positivo o negativo encontrado en cualquier etapa:

1. Abrir issue describiendo evidencia esperada vs. obtenida.
2. Convertir el caso en fixture de regresión en `tests/fixtures/` (sintético, nunca bytes del target real).
3. Ajustar detector / rúbrica heurística / prompt según corresponda.
4. Re-medir contra todos los ground truths acumulados: un ajuste no puede mejorar un target y romper otro.

## Criterios de salida (checklist)

- [x] Sitio sembrado: P = R = 1.0, cero FP, evidencia 100%. ✅ 2026-09-06, `enriqueforte.github.io/metatracer-validation`, run `adb6e8d0`
- [x] Severidad calibrada: ≥ 80% de acuerdo con el criterio humano en todos los ground truths. ✅ 5/5 exactas (100%) en el sitio sembrado, 2026-09-06
- [x] Dominio propio real escaneado y triageado al 100% (`complete: true`). ✅ 2026-09-06, `/real/` en GitHub Pages, run `1baf98dc` — P = R = 1.0, severidad 1/1 exacta

### Hallazgos de la validación (insumos para el roadmap)

- **Dedup pdfinfo+XMP verificado en producción**: un PDF real disparó `software_version` por ambas vías y se consolidó en 1 finding (`field: "pdfinfo:Producer | xmp:pdf:Producer"`).
- **EXIF eliminado "en origen" es común**: 2 de 2 fotos reales llegaron sin GPS/Make/DateTime (iOS/apps de mensajería limpian metadata). **Resuelto 2026-09-06**: foto geotagueada manualmente en lugar público (`foto-gps.jpg`, Zaragoza) — detector GPS validado con DMS racionales reales de iPhone (41.652133, -0.880942), severidad `high` exacta con agentes activos, run `67ac5d24` (P=R=1.0, severidad 2/2).
- **Candidato posterior (`author_name`)**: `Author = <nombre persona real>` en un PDF público — leak de nombre personal que no encaja en los 5 `finding_type`. v1.2 ([TASK-09](tasks/09-source-expansion.md)) lo dejó fuera a propósito: un autor con email ya dispara `email`. Añadir el tipo exigiría actualizar primero el contrato de enums en `.aicontext/tasks/README.md`.
- **iText 2.0.8 (2008)** visto en producción real (no publicado: contenido sensible del documento).
- **Autocontradicción del agente (2026-09-06, run `0b12350a`, Gemini)**: en un finding `internal_path` el agente escribió en `explanation` que la evidencia "meets the criteria for a high-severity internal path finding according to the established rubric" y aun así asignó `severity: medium`. El guard (que solo puede bajar o rechazar) dejó pasar el downgrade. **Cerrado en v1.1 / TASK-08**: el validador post-LLM rechaza salidas cuya explicación cite un nivel de rúbrica distinto del asignado. Decisión del operador: el ground truth se mantiene en `high` (la rúbrica es la fuente de verdad). Acuerdo con agentes activos: 4/5 = 80%, en el umbral del plan.
- **Evidence guard verificado en producción** (mismo run): detectó y reintentó una cita de evidencia alucinada en el mismo finding — el guard funciona fuera de los tests.
- **LOOP COMPLETO verificado (2026-09-06)**: el scan de 8 fotos oficiales Artemis II (NASA, run `371dcf9a`) produjo 7 FP de `debug_comment` sobre el caption público `xmp:dc:description` ("Artemis II **test** flight" — keyword débil TEST sobre prosa). Loop ejecutado: documentado → fixtures de regresión (`caption-long.jpg` limpio + `weak-keyword.jpg` positivo) → fix en `detectors/debug.py` (keywords débiles solo en campos ≤100 chars) → 277 tests verdes → re-verificado en vivo: sitio semilla P=R=1.0 con 6 findings (run `7f22662d`) y NASA P=R=1.0 con los 8 `software_version` intactos y **cero FP** (run `ee2d5d11`, severidad 8/8).
- **Cuota free tier de Gemini**: ~15 análisis seguidos agotan el rate limit (429); el fallback heurístico absorbe el resto sin tumbar el run (regla #5 cumplida 4 veces en producción). Para scans grandes: espaciar runs o pasar a tier de pago.
- **Etapa 0.3 ejecutada sobre NASA VDP** (DTIC descartado: su WAF bloquea clientes no-navegador y no se evade). 2 targets triageados (NTRS PDFs + images-assets). Hallazgos reales: `Mac OS X 10.2.8 Quartz PDFContext`, `Adobe PDF Library 17.11.238`, `Adobe Photoshop 25.12`/`Lightroom 9.2` en fotos oficiales — todos `low`, **no enviados** por motivo documentado: version disclosure sin exploitabilidad = informational en la política de NASA (y de la mayoría de programas). El reporte enviable sigue pendiente de un hallazgo GPS/email/path en scope.
- **Caza manual desde la Web UI (2026-09-06, operador)**: DoD VDP in-scope. Scan Army PDFs (run `40392652`): 1 finding `software_version` `Adobe PDF Library 24.5.197` (low, informational — no enviar); 2 assets `failed` por DNS (`cannot resolve tjaglcs.army.mil`, `adminpubs.tradoc.army.mil`) — el run completó (regla #5). Scan `media.defense.gov` (run `88951eeb`): 3/3 HTTP 403, 0 findings (silencio correcto: no se analizó lo que no se descargó). **No se evade WAF ni DNS.** La UI mostró Asset issues sin tumbar el run.
- **WAF de apps.dtic.mil bloquea clientes no-navegador** (2026-09-06, run `fe2fb4a6`): los 5 PDFs devolvieron HTTP 403 al cliente honesto de MetaTracer. El pipeline degradó exactamente como exige la regla #5 (5 assets `failed`, run completado limpio, reporte generado). **Decisión**: NO se evade el WAF (spoofing de UA sería contrario al "do no harm" del VDP y a nuestras reglas); DTIC queda descartado como target desde este cliente y se busca otro programa con superficie documental API-friendly.
- [x] Al menos un scan de programa bug bounty in-scope triageado; si hubo hallazgos, reporte enviado o motivo documentado. ✅ 2026-09-06, NASA VDP (2 targets, 10 hallazgos reales triageados); no enviados por ser version disclosure informational — motivo documentado en "Hallazgos de la validación"
- [x] Histórico de `validation/results/` sin regresiones entre ajustes. ✅ Post-fix: `2026-09-06-seeded-post-fix.json` (P=R=1.0, 5 tipos) y `2026-09-06-nasa-images-post-fix.json` (P=R=1.0, 8/8 software_version, 0 FP). El loop NASA→fixture→fix no rompió el sitio semilla ni el ground truth real.
- [x] Los 4–5 tipos de hallazgo confirmados con evidencia (criterio #1 del PRD). ✅ Sitio de prueba autorizado (`enriqueforte.github.io/metatracer-validation`): gps, email, internal_path, software_version, debug_comment con P=R=1.0. En documentos no sintéticos: gps (foto iPhone propia) y software_version (PDF propio + NASA). email / internal_path / debug_comment en terceros queda como caza continua, no como puerta de v1.0 — el PRD admite fixtures autorizados que cubran los cinco tipos.

**v1.0, v1.1 y v1.2 cerrados.** Siguiente fase de producto: [v2.0 Plataforma](features/10-timeline-and-roadmap.md).
