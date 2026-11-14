"""Smoke: extract lab media and print detector hits. Run from repo root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAB = Path(__file__).resolve().parents[1]
MEDIA = LAB / "public" / "media"


def _items(asset: str, fields):
    from metatracer.db.models import RawMetadataItem

    return [
        RawMetadataItem(
            asset_id=asset, namespace=field.namespace, key=field.key, value=field.value
        )
        for field in fields
    ]


def main() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from metatracer.detectors.registry import DetectorRegistry
    from metatracer.extractors.headers import extract_http_headers
    from metatracer.extractors.html import HtmlMetadataExtractor
    from metatracer.extractors.image import ImageMetadataExtractor
    from metatracer.extractors.javascript import JavaScriptMetadataExtractor
    from metatracer.extractors.office import OfficeMetadataExtractor
    from metatracer.extractors.pdf import PdfMetadataExtractor
    from metatracer.extractors.svg import SvgMetadataExtractor

    registry = DetectorRegistry()
    rows = []

    image = ImageMetadataExtractor()
    for name in ("grua4.jpg", "rambla.jpg", "bahia.png", "mercado.webp", "marea.gif"):
        rows.extend(_items(name, image.extract(MEDIA / name)))

    pdf_path = MEDIA / "acta-terminal.pdf"
    rows.extend(_items("acta-terminal.pdf", PdfMetadataExtractor().extract(pdf_path)))
    office = OfficeMetadataExtractor()
    rows.extend(_items("junta.docx", office.extract((MEDIA / "junta.docx").read_bytes())))
    odt = office.extract((MEDIA / "bitacora.odt").read_bytes())
    rows.extend(_items("bitacora.odt", odt))
    svg = SvgMetadataExtractor().extract((MEDIA / "marca.svg").read_bytes())
    rows.extend(_items("marca.svg", svg))
    js_src = (LAB / "public" / "app.js").read_text(encoding="utf-8")
    rows.extend(_items("app.js", JavaScriptMetadataExtractor().extract(js_src)))
    html = (LAB / "index.html").read_text(encoding="utf-8")
    rows.extend(_items("index.html", HtmlMetadataExtractor().extract(html)))
    rows.extend(
        _items(
            "headers",
            extract_http_headers(
                {
                    "Server": "Microsoft-IIS/10.0",
                    "X-Powered-By": "ASP.NET",
                    "X-AspNet-Version": "4.0.30319",
                    "X-Backend-Server": "cms.puertomontevideo.internal",
                    "X-Debug": "staging-token-lab-only",
                    "X-Generator": "WordPress 6.4.2",
                }
            ),
        )
    )

    drafts = registry.detect_all(rows)
    found = sorted({draft.finding_type.value for draft in drafts})
    print("types:", ", ".join(found))
    for draft in drafts:
        kind = draft.finding_type.value
        snippet = draft.evidence_snippet[:90]
        print(f"  {kind:20} {draft.field_source:28} {snippet}")
    expected = {
        "gps",
        "email",
        "internal_path",
        "software_version",
        "debug_comment",
        "internal_endpoint",
        "cloud_storage",
        "secret",
    }
    missing = expected - set(found)
    if missing:
        raise SystemExit(f"missing finding types: {sorted(missing)}")

    built = LAB / "dist" / "index.html"
    if built.exists():
        home_html = built.read_text(encoding="utf-8")
        for href in (
            "/media/grua4.jpg",
            "/media/acta-terminal.pdf",
            "/media/mercado.webp",
            "/app.js",
        ):
            if href not in home_html:
                raise SystemExit(f"prerendered home missing {href}")


if __name__ == "__main__":
    main()
