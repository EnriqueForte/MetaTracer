# Walkthrough de diez minutos

**Proyecto:** MetaTracer  
**Audiencia:** entrevista técnica o demo del MVP  
**Estado del producto:** v1.0–v1.2 cerrados. Siguiente fase: [v2.0 Plataforma](features/10-timeline-and-roadmap.md).

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

## 4. SQLite ahora, PostgreSQL + pgvector después (1 min)

El hunter corre esto en su máquina. SQLite evita ops. El schema no usa tipos exclusivos
de SQLite (UUIDs como `str`, timestamps UTC) para no bloquear el paso a PostgreSQL +
pgvector que RAG (v2.1+) necesita. Un solo writer: los scans de la API van en serie.
[Requisitos técnicos](features/07-technical-requirements.md).

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

## Cómo demostrarlo

```bash
python -m metatracer scan example.com -s example.com -y
python -m metatracer serve
```

Scope nunca se infiere. `-y` confirma autorización. Docker: `docker compose up --build`.
Suite: `pytest` (e2e usa loopback **solo** con el flag de test).
