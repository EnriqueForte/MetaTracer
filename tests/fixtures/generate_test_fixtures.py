"""Synthetic fixture factory (TASK-07, subtask 7.1): authorized test files only.

Every fixture is generated locally with Pillow/piexif/pypdf — nothing is
downloaded and nothing comes from a real target. The planted leaks use the
reserved test domain ``acme-corp.test`` (RFC 2606 style: never a real
engagement) and synthetic users/paths.

Run it to (re)generate the on-disk copies under ``tests/fixtures/files/``::

    python -m tests.fixtures.generate_test_fixtures

The e2e mock origin (:mod:`tests.fixtures.mock_origin`) builds the same bytes
in memory through :func:`build_fixture_files`, so the suite never depends on
the script having been run; the on-disk copies exist for manual inspection
and for the demo walkthrough (serve the directory and scan it with the
loopback test flag, see ``tests/README.md``).

Each "dirty" fixture is crafted to trigger EXACTLY its own detector, so the
factory test can assert a precise finding-type set per file and the clean
pair must yield zero findings.
"""

import argparse
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import piexif
from PIL import Image

from metatracer.db.models import FindingType
from tests.fixtures.builders import make_pdf_bytes

FIXTURES_DIR = Path(__file__).parent / "files"

# Reserved test domain (never a real target) and the planted leak values.
TEST_DOMAIN = "acme-corp.test"
TEST_EMAIL = f"security.lead@{TEST_DOMAIN}"
GPS_LATITUDE = 40.4168  # DMS 40 25' 0.48" N (Puerta del Sol, Madrid)
GPS_LONGITUDE = -3.7038  # DMS 3 42' 13.68" W
INTERNAL_PATH = r"C:\Users\dev_admin\Projects\ConfidentialApp\build.pdf"
SOFTWARE_PRODUCER = "Apache FOP Version 2.4"
DEBUG_COMMENT = "TODO: delete staging API key before public release - JIRA-4412"

_CONTENT_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg"}

# XMP packets: each carries only what its fixture needs — a versioned
# CreatorTool or an email in dc:creator would leak into other detectors.
_EMAIL_XMP = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:creator>
    <rdf:Seq>
     <rdf:li>Security Lead</rdf:li>
    </rdf:Seq>
   </dc:creator>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

_PATH_XMP = f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
   xmpMM:DocumentID="{INTERNAL_PATH}"/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

_SOFTWARE_XMP = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   xmp:CreatorTool="Acme Writer"/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

_CLEAN_XMP = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
   xmp:CreatorTool="Acme Writer"
   xmpMM:DocumentID="uuid:clean-0001">
   <dc:creator>
    <rdf:Seq>
     <rdf:li>Jane Doe</rdf:li>
    </rdf:Seq>
   </dc:creator>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def _save_jpeg(exif_dict: dict[str, dict[int, object]], *, color: tuple[int, int, int]) -> bytes:
    """Minimal JPEG with exactly the given EXIF IFDs (no GPS unless passed in)."""
    img = Image.new("RGB", (8, 8), color)
    buffer = io.BytesIO()
    img.save(buffer, "jpeg", exif=piexif.dump(exif_dict))
    return buffer.getvalue()


def build_gps_jpeg() -> bytes:
    """Fixture 1: EXIF GPS lat 40.4168 / lon -3.7038 (DMS rationals), no other leaks."""
    return _save_jpeg(
        {
            "0th": {
                piexif.ImageIFD.Make: b"Canon",
                piexif.ImageIFD.Model: b"Canon EOS 80D",
                piexif.ImageIFD.Artist: b"Jane Doe",
                piexif.ImageIFD.DateTime: b"2024:06:01 09:30:00",
            },
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2024:06:01 09:29:58"},
            "GPS": {
                piexif.GPSIFD.GPSLatitudeRef: b"N",
                piexif.GPSIFD.GPSLatitude: ((40, 1), (25, 1), (48, 100)),
                piexif.GPSIFD.GPSLongitudeRef: b"W",
                piexif.GPSIFD.GPSLongitude: ((3, 1), (42, 1), (1368, 100)),
            },
        },
        color=(200, 30, 30),
    )


def build_email_pdf() -> bytes:
    """Fixture 2: /Author and /Creator are the security lead's corporate email."""
    return make_pdf_bytes(
        author=TEST_EMAIL,
        creator=TEST_EMAIL,
        producer=None,  # a versioned producer would also fire software_version
        title="Q3 Security Review",
        xmp_packet=_EMAIL_XMP,
    )


def build_internal_path_pdf() -> bytes:
    """Fixture 3: the Windows build path leaks through xmpMM:DocumentID."""
    return make_pdf_bytes(
        author="dev_admin",
        # NB: no "build" in the creator name — the software detector treats
        # "build <token>" as an explicit build string (see detectors/software.py).
        creator="Acme Publishing Studio",
        producer=None,
        title="ConfidentialApp Build Notes",
        xmp_packet=_PATH_XMP,
    )


def build_software_pdf() -> bytes:
    """Fixture 4: /Producer = 'Apache FOP Version 2.4' (name + numeric version)."""
    return make_pdf_bytes(
        author="Jane Doe",
        creator="Acme Writer",
        producer=SOFTWARE_PRODUCER,
        title="Public Whitepaper",
        xmp_packet=_SOFTWARE_XMP,
    )


def build_debug_jpeg() -> bytes:
    """Fixture 5: EXIF ImageDescription with a TODO + JIRA leftover; no GPS block."""
    return _save_jpeg(
        {
            "0th": {
                piexif.ImageIFD.Make: b"Acme",
                piexif.ImageIFD.Model: b"AcmeCam 2000",
                piexif.ImageIFD.ImageDescription: DEBUG_COMMENT.encode("utf-8"),
                piexif.ImageIFD.DateTime: b"2024:06:02 17:45:00",
            },
        },
        color=(30, 30, 200),
    )


def build_caption_jpeg() -> bytes:
    """Fixture 7a: long public caption containing a weak keyword ("test flight").

    Regression for the false-positive class found in Phase-0 validation against
    NASA's public image library: prose captions must NOT fire the debug
    detector (weak keywords require short fields, see detectors/debug.py).
    """
    caption = (
        "The SLS (Space Launch System) rocket lifts off on the agency's Artemis II "
        "test flight, April 1 from Launch Complex 39B at the Kennedy Space Center, "
        "as seen from the press site."
    )
    return _save_jpeg(
        {"0th": {piexif.ImageIFD.ImageDescription: caption.encode("utf-8")}},
        color=(200, 200, 30),
    )


def build_weak_keyword_jpeg() -> bytes:
    """Fixture 7b: short field with a lone weak keyword — must still fire.

    Positive control for the length gate: a terse "INTERNAL" leftover is a real
    debug-comment finding (rubric: isolated weak keyword -> info severity).
    """
    return _save_jpeg(
        {"0th": {piexif.ImageIFD.ImageDescription: b"INTERNAL"}},
        color=(200, 30, 200),
    )


def build_clean_pdf() -> bytes:
    """Fixture 6a: sanitized PDF — metadata present, but nothing the detectors flag."""
    return make_pdf_bytes(
        author="Jane Doe",
        creator="Acme Writer",  # no version: stays raw metadata, not a finding
        producer="Acme PDF Tools",  # no version either
        title="Public Brochure",
        xmp_packet=_CLEAN_XMP,
    )


def build_clean_jpeg() -> bytes:
    """Fixture 6b: sanitized JPEG — EXIF without GPS, versioned software or comments."""
    return _save_jpeg(
        {
            "0th": {
                piexif.ImageIFD.Make: b"Acme",
                piexif.ImageIFD.Model: b"AcmeCam 2000",
                piexif.ImageIFD.Software: b"Acme Camera Firmware",  # version-less: no finding
                piexif.ImageIFD.Artist: b"Jane Doe",
                piexif.ImageIFD.DateTime: b"2024:06:03 08:15:00",
            },
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2024:06:03 08:14:59"},
        },
        color=(30, 200, 30),
    )


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    """One synthetic file: how to build it and the detector types it must trigger."""

    name: str
    filename: str
    builder: Callable[[], bytes]
    expected_types: frozenset[FindingType]

    @property
    def content_type(self) -> str:
        return _CONTENT_TYPES[Path(self.filename).suffix.lower()]


FIXTURE_SPECS: tuple[FixtureSpec, ...] = (
    FixtureSpec("gps", "gps-photo.jpg", build_gps_jpeg, frozenset({FindingType.gps})),
    FixtureSpec("email", "email-leak.pdf", build_email_pdf, frozenset({FindingType.email})),
    FixtureSpec(
        "internal-path",
        "internal-path.pdf",
        build_internal_path_pdf,
        frozenset({FindingType.internal_path}),
    ),
    FixtureSpec(
        "software",
        "software-version.pdf",
        build_software_pdf,
        frozenset({FindingType.software_version}),
    ),
    FixtureSpec(
        "debug", "debug-comment.jpg", build_debug_jpeg, frozenset({FindingType.debug_comment})
    ),
    FixtureSpec("caption-long", "caption-long.jpg", build_caption_jpeg, frozenset()),
    FixtureSpec(
        "weak-keyword",
        "weak-keyword.jpg",
        build_weak_keyword_jpeg,
        frozenset({FindingType.debug_comment}),
    ),
    FixtureSpec("clean-pdf", "clean.pdf", build_clean_pdf, frozenset()),
    FixtureSpec("clean-jpeg", "clean.jpg", build_clean_jpeg, frozenset()),
)

#: The fixtures linked from the mock origin's clean page (zero findings expected).
CLEAN_FILENAMES = tuple(spec.filename for spec in FIXTURE_SPECS if not spec.expected_types)


def build_fixture_files() -> dict[str, bytes]:
    """All fixtures as ``{filename: bytes}``, built fresh in memory."""
    return {spec.filename: spec.builder() for spec in FIXTURE_SPECS}


def spec_for(filename: str) -> FixtureSpec:
    """The spec for one fixture filename; KeyError for unknown names."""
    return next(spec for spec in FIXTURE_SPECS if spec.filename == filename)


def main(output_dir: Path = FIXTURES_DIR) -> list[Path]:
    """Write every fixture (plus an index.html manifest) to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, data in build_fixture_files().items():
        path = output_dir / filename
        path.write_bytes(data)
        written.append(path)
    manifest = output_dir / "index.html"
    manifest.write_text(_render_manifest(), encoding="utf-8")
    written.append(manifest)
    return written


def _render_manifest() -> str:
    """Simple HTML index of the fixtures (handy to serve the dir manually)."""
    rows = "\n".join(
        f'    <li><a href="{spec.filename}">{spec.filename}</a> — '
        f"expects: {', '.join(sorted(t.value for t in spec.expected_types)) or 'clean'}</li>"
        for spec in FIXTURE_SPECS
    )
    return (
        "<!doctype html>\n<html><head><title>MetaTracer test fixtures</title></head>"
        f"<body>\n  <h1>MetaTracer synthetic fixtures (authorized test files only)</h1>\n"
        f"  <ul>\n{rows}\n  </ul>\n</body></html>\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=FIXTURES_DIR,
        help=f"where to write the fixtures (default: {FIXTURES_DIR})",
    )
    args = parser.parse_args()
    for written_path in main(args.output_dir):
        print(f"wrote {written_path}")
