"""Hand-written minimal file builders for TASK-01 tests.

The full synthetic factory (many formats, sizes and edge cases) is TASK-07;
these builders cover exactly what the TASK-01 unit tests need. Everything is
built in memory and returned as bytes — tests write them to tmp_path when an
extractor needs a real file, or serve them directly from the mock transport.
"""

import io

import piexif
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pypdf import PdfWriter

XMP_PACKET = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
   xmp:CreatorTool="UnitTest Studio 9.1"
   xmpMM:DocumentID="uuid:1234-5678">
   <dc:creator>
    <rdf:Seq>
     <rdf:li>Jane Doe</rdf:li>
    </rdf:Seq>
   </dc:creator>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def make_pdf_bytes(
    *,
    author: str | None = "Jane Doe",
    creator: str | None = "UnitTest Word",
    producer: str | None = "Apache FOP 2.4",
    title: str | None = "Quarterly report",
    creation_date: str | None = "D:20240101120000+02'00'",
    xmp_packet: str | None = XMP_PACKET,
    encrypt_password: str | None = None,
    extra_info: dict[str, str] | None = None,
) -> bytes:
    """Minimal one-page PDF with an Info dictionary and an optional XMP stream.

    ``extra_info`` adds custom Info entries (keys with or without the leading
    ``/``) — where the TASK-02 detector tests plant leaks.
    """
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    metadata = {
        "/Title": title,
        "/Author": author,
        "/Creator": creator,
        "/Producer": producer,
        "/CreationDate": creation_date,
    }
    for key, value in (extra_info or {}).items():
        metadata[key if key.startswith("/") else f"/{key}"] = value
    writer.add_metadata({key: value for key, value in metadata.items() if value is not None})
    if xmp_packet is not None:
        writer.xmp_metadata = xmp_packet.encode("utf-8")
    if encrypt_password is not None:
        writer.encrypt(encrypt_password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_jpeg_bytes(*, with_exif: bool = True) -> bytes:
    """Minimal JPEG; by default with EXIF fields and a raw GPS block (DMS rationals)."""
    img = Image.new("RGB", (8, 8), (200, 30, 30))
    buffer = io.BytesIO()
    if not with_exif:
        img.save(buffer, "jpeg")
        return buffer.getvalue()
    exif = {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"Canon EOS 80D",
            piexif.ImageIFD.Software: b"TestSoft 1.0",
            piexif.ImageIFD.Artist: b"Jane Doe",
            piexif.ImageIFD.ImageDescription: b"Quarterly offsite",
            piexif.ImageIFD.DateTime: b"2024:01:01 12:00:00",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2024:01:01 11:58:00",
            piexif.ExifIFD.LensModel: b"EF-S 18-55mm",
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((40, 1), (24, 1), (4635, 100)),
            piexif.GPSIFD.GPSLongitudeRef: b"W",
            piexif.GPSIFD.GPSLongitude: ((3, 1), (42, 1), (7900, 100)),
        },
    }
    img.save(buffer, "jpeg", exif=piexif.dump(exif))
    return buffer.getvalue()


def make_png_bytes(*, xmp_packet: str | None = XMP_PACKET) -> bytes:
    """Minimal PNG carrying the XMP packet in an iTXt chunk (XML:com.adobe.xmp)."""
    img = Image.new("RGB", (8, 8), (30, 200, 30))
    pnginfo = PngInfo()
    if xmp_packet is not None:
        pnginfo.add_itxt("XML:com.adobe.xmp", xmp_packet)
    buffer = io.BytesIO()
    img.save(buffer, "png", pnginfo=pnginfo)
    return buffer.getvalue()
