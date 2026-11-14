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

`public/media/` no va al git: hay que generar fotos y actas antes del preview.
Abre `http://127.0.0.1:4173` (si el puerto está ocupado, Vite elige el
siguiente). MetaTracer **no puede escanear loopback** en runtime de producto.
El deploy público queda fuera de esta slice.

En desarrollo (`npm run dev`) el HTML es SPA; el crawler de MetaTracer necesita
el preview prerenderizado.

`generate_media.py` baja fotos de Wikimedia Commons (hace falta red la primera
vez; quedan en `.cache/`). Créditos: [CREDITS.md](CREDITS.md).

## Qué hay plantado

Ver [PLANTED.md](PLANTED.md).
