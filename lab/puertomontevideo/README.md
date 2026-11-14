# Puertomontevideo (lab)

Semanario portuario **ficticio** para ejercitar MetaTracer. No es la Web UI
del producto (`web/`). No sustituye `tests/fixtures/mock_origin.py`.

## Levantar en local

Desde la raíz del repo:

```bash
.venv/Scripts/python.exe lab/puertomontevideo/generate_media.py
cd lab/puertomontevideo
npm install
npm run build
npm run preview
```

`public/media/` no va al git: hay que generar fotos y actas antes del preview
o del deploy. En desarrollo (`npm run dev`) el HTML es SPA; el crawler necesita
el preview prerenderizado o el host público.

## Host público (spec 54)

URL viva (Cloudflare Workers, cabeceras `X-*` de recon):

https://puertomontevideo-lab.serious-radius.workers.dev

Ese deploy es de una **cuenta temporal**: hay que **reclamarla en 60 minutos**
(enlace `claim-preview` que imprime Wrangler) o Cloudflare la borra. Después:
`npx wrangler login` y deploys sin `--temporary`.

En MetaTracer (crawl HTTP, no loopback):

- Objetivo: `https://puertomontevideo-lab.serious-radius.workers.dev`
- Alcance: `puertomontevideo-lab.serious-radius.workers.dev` (el host entero;
  no uses `workers.dev`)
- Confirmar scope a mano

Para republicar el `dist/` local:

```bash
npx wrangler deploy ./dist --name puertomontevideo-lab --temporary --compatibility-date 2026-11-14
```

(Tras reclamar la cuenta, quita `--temporary`.)

`generate_media.py` baja fotos de Wikimedia Commons (hace falta red la primera
vez; quedan en `.cache/`). Créditos: [CREDITS.md](CREDITS.md).

## Qué hay plantado

Ver [PLANTED.md](PLANTED.md).
