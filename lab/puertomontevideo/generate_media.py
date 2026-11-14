"""Synthetic media for the Puertomontevideo lab target (TASK-53).

Photos: Wikimedia Commons (see CREDITS.md). Document bodies are invented.
Planted metadata matches MetaTracer detectors and is not a real credential.
"""

from __future__ import annotations

import argparse
import io
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

import piexif
from PIL import Image
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "public" / "media"
CACHE = ROOT / ".cache"
_USER_AGENT = (
    "PuertomontevideoLab/1.0 (MetaTracer synthetic news target; educational)"
)

# Thumbnails from Wikimedia Commons (CC BY / BY-SA). See CREDITS.md.
_COMMONS: dict[str, str] = {
    "aereo": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/"
        "Puerto_de_Montevideo_a%C3%A9reo.jpg/1280px-Puerto_de_Montevideo_a%C3%A9reo.jpg"
    ),
    "rambla": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/56/"
        "Puerto_de_Montevideo%2C_Uruguay.jpg/1280px-Puerto_de_Montevideo%2C_Uruguay.jpg"
    ),
    "bahia": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/"
        "Puerto_de_Montevideo_en_2019.jpg/1280px-Puerto_de_Montevideo_en_2019.jpg"
    ),
    "mercado": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/"
        "2016_Mercado_del_Puerto_de_Montevideo.jpg/"
        "1280px-2016_Mercado_del_Puerto_de_Montevideo.jpg"
    ),
}

# Puerto de Montevideo (hito público, no una vivienda).
GPS_LAT = -34.9014
GPS_LON = -56.2117
EMAIL = "redaccion@puertomontevideo.press"
INTERNAL_PATH = r"C:\Users\mesa_puerto\ActasTerminal\junta-2026.docx"
INTERNAL_HOST = "cms.puertomontevideo.internal"
CLOUD_URI = "s3://puertomontevideo-media-staging/actas/2026-03.pdf"
AKIA = "AKIATESTPMVDLAB00001"
GHP = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
JWT = (
    "eyJhbGciOiJIUzI1NiJ9."
    "eyJpc3MiOiJwdWVydG9tb250ZXZpZGVvLWxhYiJ9."
    "labSyntheticSignatureX"
)
PEM_BEGIN = "-----BEGIN RSA PRIVATE KEY-----"
SOFTWARE_PDF = "Apache FOP Version 2.4"


def _fetch_commons(key: str) -> Image.Image:
    """Download (or reuse cache) a Commons still; RGB, original EXIF dropped."""
    url = _COMMONS[key]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{key}.bin"
    if not cache_path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                time.sleep(1.5 * (attempt + 1))
                with urllib.request.urlopen(request, timeout=60) as response:
                    cache_path.write_bytes(response.read())
                last_error = None
                break
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 503}:
                    break
            except urllib.error.URLError as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(
                f"cannot fetch Commons still {key}: {last_error}"
            ) from last_error
    with Image.open(io.BytesIO(cache_path.read_bytes())) as src:
        return src.convert("RGB")


def _cover(
    img: Image.Image,
    size: tuple[int, int],
    focus: tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / img.width, target_h / img.height)
    resized = img.resize(
        (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
        Image.Resampling.LANCZOS,
    )
    max_left = max(0, resized.width - target_w)
    max_top = max(0, resized.height - target_h)
    left = min(max_left, max(0, int(max_left * focus[0])))
    top = min(max_top, max(0, int(max_top * focus[1])))
    return resized.crop((left, top, left + target_w, top + target_h))


def _decimal_to_dms(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    abs_v = abs(value)
    degrees = int(abs_v)
    minutes_full = (abs_v - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    sec_num = int(round(seconds * 100))
    return ((degrees, 1), (minutes, 1), (sec_num, 100))


def _save_jpeg(img: Image.Image, exif_dict: dict[str, dict[int, object]] | None = None) -> bytes:
    buffer = io.BytesIO()
    if exif_dict:
        img.save(buffer, "jpeg", quality=86, exif=piexif.dump(exif_dict))
    else:
        img.save(buffer, "jpeg", quality=86)
    return buffer.getvalue()


def _iptc_block(datasets: dict[tuple[int, int], bytes]) -> bytes:
    payload = bytearray()
    for (record, dataset), value in datasets.items():
        payload.append(0x1C)
        payload.append(record)
        payload.append(dataset)
        payload.extend(len(value).to_bytes(2, "big"))
        payload.extend(value)
    irb = bytearray(b"8BIM")
    irb.extend((0x0404).to_bytes(2, "big"))
    irb.extend(b"\x00\x00")
    irb.extend(len(payload).to_bytes(4, "big"))
    irb.extend(payload)
    if len(payload) % 2:
        irb.append(0)
    body = b"Photoshop 3.0\x00" + bytes(irb)
    return b"\xff\xed" + (len(body) + 2).to_bytes(2, "big") + body


def _jpeg_insert_app13(jpeg: bytes, app13: bytes) -> bytes:
    if not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("not a jpeg")
    pos = 2
    insert_at = 2
    while pos + 4 <= len(jpeg) and jpeg[pos] == 0xFF:
        marker = jpeg[pos + 1]
        if marker in {0xDA, 0xD9}:  # SOS / EOI
            break
        if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = int.from_bytes(jpeg[pos + 2 : pos + 4], "big")
        next_pos = pos + 2 + length
        if 0xE0 <= marker <= 0xEF:
            insert_at = next_pos
        pos = next_pos
    return jpeg[:insert_at] + app13 + jpeg[insert_at:]


def build_grua_jpeg() -> bytes:
    img = _cover(_fetch_commons("aereo"), (1280, 720), focus=(0.48, 0.28))
    lat = _decimal_to_dms(GPS_LAT)
    lon = _decimal_to_dms(GPS_LON)
    return _save_jpeg(
        img,
        {
            "0th": {
                piexif.ImageIFD.Make: b"Canon",
                piexif.ImageIFD.Model: b"Canon EOS 80D",
                piexif.ImageIFD.Artist: b"Mesa del Muelle",
                piexif.ImageIFD.DateTime: b"2026:03:12 07:40:00",
            },
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:03:12 07:39:51"},
            "GPS": {
                piexif.GPSIFD.GPSLatitudeRef: b"S",
                piexif.GPSIFD.GPSLatitude: lat,
                piexif.GPSIFD.GPSLongitudeRef: b"W",
                piexif.GPSIFD.GPSLongitude: lon,
            },
        },
    )


def build_rambla_jpeg() -> bytes:
    img = _cover(_fetch_commons("rambla"), (1200, 675), focus=(0.4, 0.72))
    jpeg = _save_jpeg(img)
    iptc = _iptc_block(
        {
            (2, 80): EMAIL.encode("utf-8"),
            (2, 90): b"Montevideo",
            (2, 92): b"Rambla 25 de Agosto de 1825, Ciudad Vieja",
            (2, 120): b"Vista al puerto desde Ciudad Vieja. Uso interno del semanario.",
        }
    )
    return _jpeg_insert_app13(jpeg, iptc)


def _xmp_gps_packet() -> str:
    return f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:exif="http://ns.adobe.com/exif/1.0/"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   exif:GPSLatitude="{GPS_LAT:.6f}"
   exif:GPSLongitude="{GPS_LON:.6f}">
   <dc:description>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">Bahia y TCP. Staging {CLOUD_URI}</rdf:li>
    </rdf:Alt>
   </dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def build_bahia_png() -> bytes:
    img = _cover(_fetch_commons("bahia"), (1100, 620), focus=(0.82, 0.42))
    pnginfo = PngInfo()
    pnginfo.add_itxt("XML:com.adobe.xmp", _xmp_gps_packet())
    buffer = io.BytesIO()
    img.save(buffer, "png", pnginfo=pnginfo)
    return buffer.getvalue()


def build_mercado_webp() -> bytes:
    img = _cover(_fetch_commons("mercado"), (1000, 560))
    buffer = io.BytesIO()
    img.save(buffer, "webp", quality=82)
    return buffer.getvalue()


def build_marea_gif() -> bytes:
    source = _fetch_commons("aereo")
    frames = []
    for i in range(3):
        inset = 20 + i * 28
        cropped = source.crop((inset, inset, source.width - inset, source.height - inset))
        frames.append(_cover(cropped, (640, 360)))
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=400,
        loop=0,
        comment=b"FIXME: leftover debug path C:\\Users\\mesa_puerto\\gifs\\marea.gif",
    )
    return buffer.getvalue()


def build_marca_svg() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="240" height="64" viewBox="0 0 240 64">
  <metadata>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
      <rdf:Description>
        <dc:creator>{EMAIL}</dc:creator>
        <dc:description>CMS interno http://{INTERNAL_HOST}/marca</dc:description>
      </rdf:Description>
    </rdf:RDF>
  </metadata>
  <rect width="240" height="64" fill="#0f4c5c"/>
  <rect x="0" y="56" width="240" height="8" fill="#d23a2e"/>
  <rect x="168" y="0" width="24" height="56" fill="#f0b429"/>
  <rect x="192" y="0" width="24" height="56" fill="#1f7a62"/>
  <text x="14" y="38" fill="#f4efe4" font-size="17"
        font-family="Georgia, serif">Puertomontevideo</text>
</svg>
""".encode()


def _acta_xmp() -> str:
    return f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
   xmpMM:DocumentID="{INTERNAL_PATH}">
   <dc:subject>
    <rdf:Bag>
     <rdf:li>{AKIA}</rdf:li>
    </rdf:Bag>
   </dc:subject>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _acta_paragraphs() -> list[str]:
    return [
        "MESA DEL MUELLE — extracto de junta (documento ficticio)",
        "No es un acta de la ANP, de TCP ni de Montecon. Texto inventado "
        "para un laboratorio de metadata. Cargos y cifras son de relleno.",
        "Sesion citada en un salon de Ciudad Vieja, entre la calle Piedras y "
        "la peatonal Sarandi, a dos cuadras de la Rambla 25 de Agosto de 1825 "
        "y del Mercado del Puerto (Perez Castellano). Frente, la Capitania.",
        "Punto 1. Terminal Cuenca del Plata, muelle C: se anoto el turno de "
        "gruas y el acceso desde la Rambla Portuaria. Punto 2. Montecon, "
        "muelle A y muelle B: cola de camiones hacia Bella Vista.",
        "Punto 3. Muelle Fluvial y Darsena Fluvial: cabotaje. Punto 4. "
        "Muelle Maciel y terminal de pasajeros: arribo inventado de un "
        "catamaran. Punto 5. Darsena I y Darsena II: buques de linea.",
        "Del lado de tierra: Barrio Sur y Palermo hacia el este; Aguada y "
        "la Estacion Central hacia el norte; Capurro, La Teja y Punta de "
        "Sayago hacia el oeste. Villa del Cerro cierra la bahia.",
        "Cierre de archivo fotografico: peatonal Sarandi, calle Buenos Aires, "
        "calle 25 de Mayo, Rambla 25 de Agosto y el espigon frente a la "
        "Capitania. Proxima nota: Muelle de Escala.",
    ]


def build_acta_pdf() -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas

    raw = io.BytesIO()
    page = pdf_canvas.Canvas(raw, pagesize=A4)
    width, height = A4
    y = height - 72
    page.setFont("Times-Bold", 14)
    page.drawString(72, y, "Acta de la junta de la terminal — marzo 2026")
    y -= 28
    page.setFont("Times-Roman", 11)
    for paragraph in _acta_paragraphs():
        for line in _wrap_line(paragraph, 88):
            if y < 72:
                page.showPage()
                page.setFont("Times-Roman", 11)
                y = height - 72
            page.drawString(72, y, line)
            y -= 16
        y -= 8
    page.save()
    raw.seek(0)
    reader = PdfReader(raw)
    writer = PdfWriter()
    for pdf_page in reader.pages:
        writer.add_page(pdf_page)
    writer.add_metadata(
        {
            "/Title": "Acta de la junta de la terminal — marzo 2026",
            "/Author": EMAIL,
            "/Creator": "Mesa del Muelle",
            "/Producer": SOFTWARE_PDF,
            "/Subject": f"{PEM_BEGIN}\nLAB-SYNTHETIC-NOT-A-KEY",
        }
    )
    writer.xmp_metadata = _acta_xmp().encode("utf-8")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _wrap_line(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join([*current, word])
        if len(trial) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def build_junta_docx() -> bytes:
    core = f"""<?xml version="1.0"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Notas de la junta</dc:title>
  <dc:creator>{EMAIL}</dc:creator>
  <dc:description>Borrador. No usar ghp token {GHP}</dc:description>
  <cp:lastModifiedBy>mesa_puerto</cp:lastModifiedBy>
</cp:coreProperties>
""".encode()
    app = b"""<?xml version="1.0"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Word 16.0</Application>
  <Company>Puertomontevideo Lab</Company>
</Properties>
"""
    types_xml = (
        b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org'
        b'/package/2006/content-types"></Types>'
    )
    notes = [
        "Notas de la junta (ficticias). No es un documento de la ANP, de TCP "
        "ni de Montecon.",
        "Recorrido a pie: peatonal Sarandí, calle Piedras, Pérez Castellano, "
        "Mercado del Puerto, Rambla 25 de Agosto de 1825, Capitanía.",
        "Muelles citados: Muelle A y B (Montecon), muelle C (TCP), Muelle "
        "Fluvial, Muelle Maciel, Muelle de Escala, Dársena I, Dársena II y "
        "Dársena Fluvial.",
        "Barrios: Ciudad Vieja, Barrio Sur, Palermo, Aguada, Capurro, Bella "
        "Vista, La Teja, Punta de Sayago, Villa del Cerro.",
        "Cierre en la terminal de pasajeros del Muelle Maciel. Cifras y "
        "turnos son inventados.",
    ]
    body = "".join(
        "<w:p><w:r><w:t xml:space='preserve'>"
        f"{_xml_escape(paragraph)}"
        "</w:t></w:r></w:p>"
        for paragraph in notes
    )
    document_xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/"
        "wordprocessingml/2006/main'><w:body>"
        f"{body}"
        "</w:body></w:document>"
    ).encode()
    return _zip_bytes(
        {
            "[Content_Types].xml": types_xml,
            "word/document.xml": document_xml,
            "docProps/core.xml": core,
            "docProps/app.xml": app,
        }
    )


def build_bitacora_odt() -> bytes:
    meta = f"""<?xml version="1.0"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink">
  <office:meta>
    <meta:generator>LibreOffice 7.6.4</meta:generator>
    <dc:title>Bitacora de muelle</dc:title>
    <dc:creator>Mesa del Muelle</dc:creator>
    <meta:template xlink:href="{INTERNAL_PATH}"/>
  </office:meta>
</office:document-meta>
""".encode()
    return _zip_bytes(
        {
            "mimetype": b"application/vnd.oasis.opendocument.text",
            "meta.xml": meta,
            "content.xml": (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<office:document-content "
                "xmlns:office='urn:oasis:names:tc:opendocument:xmlns:office:1.0' "
                "xmlns:text='urn:oasis:names:tc:opendocument:xmlns:text:1.0'>"
                "<office:body><office:text>"
                "<text:p>Bitácora de muelle (ficticia). No es un parte de la "
                "Capitanía ni de la ANP.</text:p>"
                "<text:p>Marea en la Dársena Fluvial. Prácticos hacia Villa del "
                "Cerro. Camiones por Capurro, Bella Vista y La Teja; silos en "
                "Punta de Sayago.</text:p>"
                "<text:p>Pasajeros en Muelle Maciel. Contenedores en muelle C "
                "(TCP) y muelles A/B (Montecon). Cabotaje en Muelle Fluvial y "
                "Muelle de Escala. Dársena I y Dársena II a media carga.</text:p>"
                "<text:p>Archivo fotográfico: Pérez Castellano, peatonal Sarandí, "
                "calle Buenos Aires, Rambla 25 de Agosto de 1825.</text:p>"
                "</office:text></office:body></office:document-content>"
            ).encode(),
        }
    )


ASSETS: tuple[tuple[str, Callable[[], bytes]], ...] = (
    ("grua4.jpg", build_grua_jpeg),
    ("rambla.jpg", build_rambla_jpeg),
    ("bahia.png", build_bahia_png),
    ("mercado.webp", build_mercado_webp),
    ("marea.gif", build_marea_gif),
    ("marca.svg", build_marca_svg),
    ("acta-terminal.pdf", build_acta_pdf),
    ("junta.docx", build_junta_docx),
    ("bitacora.odt", build_bitacora_odt),
)


def main(output_dir: Path = MEDIA) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, builder in ASSETS:
        path = output_dir / name
        path.write_bytes(builder())
        written.append(path)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=MEDIA)
    args = parser.parse_args()
    for path in main(args.output_dir):
        print(f"wrote {path}")
