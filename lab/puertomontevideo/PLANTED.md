# Hallazgos plantados — Puertomontevideo

Laboratorio sintético. Nada de esto es una credencial real ni PII de una
persona viva. GPS: **Puerto de Montevideo**, lat `-34.9014`, lon `-56.2117`.

Host público (spec 54): `https://puertomontevideo-lab.serious-radius.workers.dev`
(reclamar la cuenta Cloudflare en 60 min o caduca). Alcance:
`puertomontevideo-lab.serious-radius.workers.dev`.

Defaults de MetaTracer (`depth=1`, `max_pages=1`): todo lo de la tabla está
enlazado desde la portada (`/`).

| Asset | Namespaces | `finding_type` esperados |
| :--- | :--- | :--- |
| `/` (HTML + headers) | `html`, `http` | `email` (meta author), `software_version` (generator / IIS / ASP.NET), `debug_comment` (TODO/JIRA/NOT FOR PUBLIC RELEASE), `internal_endpoint` (`cms.puertomontevideo.internal`, `10.40.12.8`), `cloud_storage` (`s3://…`) |
| `/app.js` | `js` | `debug_comment` (FIXME + path), `secret` (JWT), `internal_path` |
| `/theme.css` → `url(/media/grua4.jpg)` | (encola JPEG) | ver `grua4.jpg` |
| `/media/grua4.jpg` | `exif` | `gps` |
| `/media/rambla.jpg` | `iptc` | `email` (By-line); SubLocation Rambla 25 de Agosto |
| `/media/bahia.png` | `xmp` | `gps`, `cloud_storage` |
| `/media/marea.gif` | `exif` (Comment) | `debug_comment`, `internal_path` |
| `/media/marca.svg` | `xmp` | `email`, `internal_endpoint` |
| `/media/acta-terminal.pdf` | `pdfinfo`, `xmp` | `email`, `software_version`, `internal_path`, `secret` (AKIA + PEM) |
| `/media/junta.docx` | `ooxml` | `email`, `software_version`, `secret` (`ghp_`) |
| `/media/bitacora.odt` | `odf` | `software_version`, `internal_path` |
| `/media/mercado.webp` | (raster limpio) | ninguno de detector; cubre el MIME |

Valores plantados (todos falsos):

- correo: `redaccion@puertomontevideo.press`
- path: `C:\Users\mesa_puerto\ActasTerminal\junta-2026.docx`
- AKIA: `AKIATESTPMVDLAB00001`
- ghp: `ghp_` + `abcdefghijklmnopqrstuvwxyz0123456789`
- JWT compact en comentario de `app.js`
- PEM: cabecera `BEGIN RSA PRIVATE KEY` en Subject del PDF

Fotos: Wikimedia Commons ([CREDITS.md](CREDITS.md)). Cuerpos de PDF/DOCX/ODT
inventados, con toponimia real (TCP muelle C, Montecon muelles A/B, Muelle
Fluvial, Muelle Maciel, Muelle de Escala, Dársena I/II, Rambla 25 de Agosto,
Ciudad Vieja, Pérez Castellano, Sarandí, Capurro, La Teja, Aguada, Punta de
Sayago, Villa del Cerro).
