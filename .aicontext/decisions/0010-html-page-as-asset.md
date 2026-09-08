# ADR-0010: La página HTML del crawl es un `Asset`

**Fecha:** 2026-09-06  
**Estado:** Aceptada (v1.2 / [TASK-09](../tasks/09-source-expansion.md))  
**Slice:** Expansión de fuentes

## Contexto

Hasta v1.1 el crawler fetchaba la home (profundidad 1), parseaba `<a href>` / `<img src>` y
descartaba el HTML. Title, meta generator y comentarios `<!-- TODO -->` nunca llegaban a
los detectores. Hacer un segundo GET de la misma URL duplicaría tráfico, rate-limit y
superficie SSRF.

## Decisión

`PublicDocCrawler.fetch_page` devuelve el body ya leído. La ingesta persiste esa página como
`Asset` (`namespace=html`) **sin segundo GET**. Extrae title, un set cerrado de meta tags y
comentarios HTML (salta vacíos y condicionales `<!--[if`). El HTML completo no se guarda.

La página cuenta contra `MAX_ASSETS_PER_RUN`. `<script src>` in-scope que termina en `.js`
se encola como el resto de documentos, misma profundidad 1, mismo cap.

Una URL con extensión de documento (`.pdf`, imagen) cuyo body parezca HTML sigue
`unsupported_type`: las error pages no se reciclan como assets HTML.

HTML y JS se extraen en memoria; PDF/imagen siguen yendo a un temporal que se borra en
`finally`.

## Alternativas descartadas

- **Seguir usando el HTML solo como semilla.** El crawl ya pagaba el GET; tirar title/meta
  era desperdiciar la única fuente que el hunter ve en el navegador.
- **Segundo GET “oficial” de la home.** Doble rate-limit, doble guard DNS, y el body puede
  haber cambiado entre hops (TOCTOU innecesario).
- **Parser HTML como PDF.** Magic bytes mandan en documentos. Reciclar un 404 HTML de
  `/report.pdf` inflaría findings de generator/comentarios de la error page del CDN.

## Consecuencias

- Un dominio cuya home es HTML produce al menos un asset `ok` aunque no enlace PDFs.
- Off-scope `<script src>` no abre socket (mismo `ScopeValidator` que los documentos).
- Un `.js` 404 no aborta el run (regla: un asset fallido no tumba el run).
