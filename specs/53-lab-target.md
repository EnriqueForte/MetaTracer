# Spec 53 — Target de laboratorio Puertomontevideo

**Estado:** closed  
**Agente previsto:** implementación en `lab/` (no `v2-ui-engineer`) · fábrica: `pipeline-engineer` · cierre: `docs-architect` · veto: `safety-guardian`  
**Skill al abrir:** `metadata-extraction` + `detector-patterns`  
**Task:** [.aicontext/tasks/53-lab-target.md](../.aicontext/tasks/53-lab-target.md)

## Intención

Un semanario portuario **ficticio** (`lab/puertomontevideo`) con archivos
binarios reales y metadata sintética, para que MetaTracer tenga un target
denso que cubrir todos los `finding_type` y namespaces del contrato. No es
producto. No sustituye el mock origin de tests.

Marca: **Puertomontevideo**. Relato: Montevideo y su puerto. Copy en español
rioplatense. Personas y organismos de la redacción son inventados.

## Alcance (cerrado)

- Vite + React + TypeScript, HTML prerenderizado (el crawler no ejecuta JS).
- Portada enlaza todos los assets “sucios” (defaults `depth=1`, `max_pages=1`).
- Fábrica Python de JPEG/PNG/WebP/GIF/SVG/PDF/OOXML/ODF.
- Preview local con cabeceras de la allowlist HTTP.
- `PLANTED.md`: URL → findings esperados + coords GPS del puerto.
- Banner de laboratorio: no es un medio ni una autoridad reales.

## Fuera de alcance

`src/` y `web/` de producto. `ALLOW_LOOPBACK` fuera de pytest. Deploy público
(Vercel/Netlify/VPS) y scan de MetaTracer contra este sitio (el guard bloquea
loopback). HEIC/AVIF. Sustituir fixtures unitarios. Dependencias nuevas en
`pyproject.toml`.

## Dependencias

Contratos `finding_type` / `namespace` en `.aicontext/tasks/README.md`.
Extractores y detectores ya cerrados (TASK-01–09, 37, 48, 49).
