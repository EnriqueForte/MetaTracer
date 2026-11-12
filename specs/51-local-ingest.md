# Spec 51 — Ingesta local de carpeta

**Estado:** reserved  
**Agente previsto:** `pipeline-engineer` · CLI/API: `ui-engineer` · wizard: `v2-ui-engineer`  
**Skill al abrir:** `metadata-extraction`, `metatracer-safety-rules`  
**Task:** no existe hasta que esta spec pase a `active`

## Intención

Hunters autorizados a menudo **ya tienen** documentos del programa (export, zip
descomprimido). El wizard actual solo hace crawl HTTP. Esta slice alimenta los
**mismos extractores y sniff** desde un directorio local, sin abrir red.

## Alcance previsto (cuando pase a active)

- CLI + API + UI: seleccionar directorio o lista de archivos. Recorrido de
  extensiones allowlist; magic-bytes como en ingest remota.
- `Asset.url`: esquema `file:` o path relativo estable; **cero bytes** en SQLite/
  Postgres ni en logs ni al LLM.
- Safety: este camino **no** llama a `safe_httpx_request`. Loopback irrelevante.
  Confirmación de **scope lógico** (dominio del engagement) para etiquetar findings
  y reportes; no se usa para HTTP.
- Un asset ilegible → `failed`/`skipped` y el run continúa (regla 5).
- OOXML/ODF: propiedades-only (spec 37). Un `.zip` genérico no es Office.

## Fuera de alcance

Ejecutar binarios del target. Preview/render de documentos. Unpack de `.zip`
genérico, `.rar`, `.7z`. Sembrar crawl con CDX/Wayback (posible spec 52, no esta).
Dorks. Autenticación a file shares. Código mientras esta spec esté `reserved`.

## Dependencias

Extractores actuales (PDF/imagen/HTML/JS/office). Spec 48 puede ampliar tipos;
51 no espera a 48: ingest local de lo que ya se sepa parsear.
