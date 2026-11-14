# TASK-53: Target de laboratorio Puertomontevideo

**Módulo:** `lab/puertomontevideo/`  
**Spec:** [specs/53-lab-target.md](../../specs/53-lab-target.md)  
**Dependencias:** extractores/detectores cerrados (no se modifican)  
**Agente:** implementación lab (no `v2-ui-engineer`)  
**Estado:** **Cerrada** (2026-11-14).

## 1. Objetivo técnico

Sitio de noticias sintético, prerenderizado, con binarios plantados para cada
`finding_type` y cada `namespace`. Preview solo local.

## 2. Fuera de alcance

Producto (`src/`, `web/`). Deploy público. Bypass de loopback. Enums nuevos.

## 3. DoD

- [x] `lab/puertomontevideo/PLANTED.md` cubre los 8 `finding_type` y los 9 namespaces
- [x] `python generate_media.py` escribe `public/media/`
- [x] `npm run build` deja HTML estático con `<a>`/`<img>`/`<script src>` en la portada
- [x] Preview inyecta cabeceras de recon (allowlist)
- [x] Banner de laboratorio visible
- [x] Cero secretos reales, cero PII de personas reales, GPS = puerto de Montevideo

Spec **closed**. Deploy público sigue OOS. Preview: `lab/puertomontevideo` (`generate_media.py` + `npm run build` + `npm run preview`).
