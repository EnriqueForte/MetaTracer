# Walkthrough de diez minutos

**Proyecto:** MetaTracer  
**Audiencia:** entrevista técnica o demo del MVP  
**Estado del producto:** v1.0–v1.2, v2.0, v2.1+, v2.2, v2.3 y v2.4 cerrados. **v3.0 cerrada** (watch/headless, PostgreSQL+pgvector, auth básica). **v3.1 cerrada** (multi-usuario + rediseño de la Web UI). **v3.2 cerrada** (hardening post-auditoría 2026-10-03, TASK-27 → TASK-35). Suite vérificada: **787 passed, 6 skipped** · cobertura **91.30%** (≥85% DoD) · ruff limpio.

Este recorrido no abre `src/`. Las tasks son la fuente de verdad; aquí solo el *por qué*.

## 1. Qué es (30 s)

Herramienta de descubrimiento de metadata sensible para bug bounty **autorizado**.
El hunter confirma un scope, apunta a URLs o dominios, y obtiene un reporte priorizado
(Markdown / JSON / HTML) con evidencia, impacto y remediación. No es un scraper ni un
framework de exploits. [Ética](features/08-ethics-legal-safety.md).

## 2. El pipeline (2 min)

```text
 CLI / Web UI
        │
        ▼
 Safety Gate          scope confirmado + host in-scope + IP no privada
        │
        ▼
 Ingest + Extract     PDF / imagen / HTML / headers HTTP / comentarios JS
                      → Asset + RawMetadataItem   (nunca bytes)
        │
        ▼
 Detectors            5 tipos, severity = NULL
        │
        ▼
 Classify             heurístico siempre (rúbrica + techos)
        │
        ▼
 Agents (opcional)    LangGraph; si el LLM falla → el heurístico queda
        │
        ▼
 Reports              inglés, Critical → Info
        │
        ▼
 CLI / Web UI         misma fuente de datos
```

**Por qué detección y LLM viven separados.** Los detectores son deterministas: mismo
campo, mismo finding, testable sin red. El LLM interpreta (qué significa, cuán grave,
cómo remediarlo). Si el modelo alucina, el guard post-LLM **rechaza o baja**; no puede
cambiar `finding_type` ni `evidence_snippet` ni inventar exploits.
Detalle: [TASK-02](tasks/02-specific-detection.md), [TASK-05](tasks/05-ai-agents.md).

v1.2 no añade tipos: HTML, `Server:` y comentarios JS alimentan los mismos cinco
detectores. [ADR-0009](decisions/0009-same-finding-types-new-namespaces.md).

## 3. Grafo LangGraph y fallback (1,5 min)

```text
 START → LoadNextFinding
              │ findings left
              ▼
        AnalyzeContext     (modelo fuerte, 1 finding / llamada)
              ▼
        ClassifySeverity   EvidenceGuard; si falla → heurístico TASK-03
              ▼
        DraftExplanation   título (modelo rápido) + prosa según depth
              ▼
        SaveEvaluation     persistencia fuera del grafo
              │
              └── loop ──► SynthesizeReportSummary → END
```

`reasoning_depth` (`brief` / `standard` / `detailed`) cambia la longitud de la prosa, no
la evidencia. Si no hay API key o el modelo cae, el reporte sale igual con plantillas
heurísticas (`Not generated (heuristic baseline)`). El grafo no es el orquestador del
scan: el scan es determinista; el grafo solo enriquece findings ya persistidos.

## 4. SQLite ahora, PostgreSQL + pgvector ya (1 min)

El hunter corre esto en su máquina. SQLite evita ops; desde **v3.0 (TASK-23)** se soporta
PostgreSQL + asyncpg + pgvector (Alembic gestiona el schema; `METATRACER_DATABASE_URL`).
El schema no usa tipos exclusivos de SQLite (UUIDs como `str`, timestamps UTC). Un solo
writer por defecto; concurrencia acotada con `METATRACER_MAX_CONCURRENT_RUNS` (Postgres).
[Requisitos técnicos](features/07-technical-requirements.md), [Eje B](features/12-platform-v3.md).

## 5. Contexto pequeño, menos alucinaciones (1 min)

El payload al modelo es un contrato cerrado: `finding_type`, `field_source`,
`evidence_snippet` (~150 chars), `confidence`, severidad heurística, dominio y
content-type. Nunca el EXIF completo, nunca el HTML, nunca bytes. Menos tokens = menos
sitio donde el modelo “complete” hechos. El `ContextOptimizer` recorta; el guard exige
que `cited_evidence` sea substring del snippet.

## 6. Safety: qué bloquea y qué se aceptó (2 min)

| Control | Bloquea |
| :--- | :--- |
| Confirmación de scope | Scan sin `scope_confirmed=True` |
| `ScopeValidator` | Hosts fuera de la lista; `evil-target.com` no matchea `target.com` |
| `NetworkSafetyGuard` | Loopback, RFC 1918, link-local (incl. `169.254.169.254`), CGNAT, ULA, multicast — **antes** del socket |
| Wrapper `safe_httpx_request` | Redirects off-scope (re-valida cada hop, máx. 5); no hay `httpx` crudo en extractores |
| Allowlist de tipos | PDF/imagen por magic bytes; HTML/JS por content-type/path **después** de fallar el magic |
| Allowlist de headers | Cookies / Authorization nunca llegan a SQLite |
| Asset fallido | `failed`/`skipped` + `error_message`; el run sigue |
| Loopback | Bloqueado en runtime. `METATRACER_ALLOW_LOOPBACK` solo tests |

Limitaciones **aceptadas a conciencia** (no son bugs a “arreglar” con un flag):

- **TOCTOU / DNS rebinding:** la guarda se llama justo antes de cada request; no hay pin
  de IP en el transporte.
- **Sin Public Suffix List:** `foo.co.uk` se trata como dominio opaco.
- **Un solo writer SQLite.**
- **Crawl superficial:** profundidad 1, no bot a escala, no robots.txt completo.

No hay `--insecure` en la distribución por defecto.

## 7. v1.2 en una frase (1 min)

La home HTML que ya se fetchaba se persiste como asset ([ADR-0010](decisions/0010-html-page-as-asset.md));
las cabeceras de recon de cualquier descarga `ok` van al namespace `http`
([ADR-0011](decisions/0011-http-header-allowlist.md)); los comentarios de scripts inline y
`.js` in-scope van a `js`. Cero `finding_type` nuevos. Cero dependencias runtime nuevas.
`author_name` sigue fuera.

## 7. v3.1 y v3.2 en una frase (1 min)

**v3.1** añadió multi-usuario (first-run setup, panel de admin, invitaciones de un solo uso)
y el rediseño visual de la Web UI (design system `.mt-*`, Tailwind compilado offline y
Alpine CSP vendored en `/static`, sin CDN). **v3.2** cerró el hardening de la auditoría de
2026-10-03: `trust_env=False` (P0-1), auth obligatoria en bind público, HMAC real en
webhooks, CSV anti-fórmula, tope pre-inflate de XMP, recovery/abort de runs, integridad del
agente (guard de prosa, techo con feedback), retención GDPR, authz del API, higiene de
core/backend, precisión de detectores y las mejoras UI/UX de Web V2 (triage, filtros por URL,
mapa GPS, comparación de runs, light mode).

## Cómo demostrarlo

```bash
python -m metatracer scan example.com -s example.com -y
python -m metatracer serve                          # auth OFF por defecto en loopback
METATRACER_AUTH_ENABLED=true python -m metatracer serve   # v3.0+: login + CSRF
python -m metatracer watch <scope-id> --once                      # v3.0: una iteración
python -m metatracer watch <scope-id> --interval 21600 --webhook <id>  # v3.0: deltas continuos
```

Scope nunca se infiere. `-y` confirma autorización. Docker: `docker compose up --build`
(auth ON por defecto en el contenedor). Suite: `pytest` (e2e usa loopback **solo** con el
flag de test; tests Postgres se skipean sin servidor).
