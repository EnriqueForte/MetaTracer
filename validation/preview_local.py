"""Local pre-upload preview: what would MetaTracer find in these files?

Runs the real extractors and detectors on local files — no network, no
database, no LLM, nothing persisted — so you can see exactly which metadata
leaks BEFORE publishing the files to your validation site. This is the
privacy gate of Phase 0.2: anything shown here WILL be public if you upload
the file.

    .venv\\Scripts\\python.exe -m validation.preview_local C:\\path\\to\\doc.pdf C:\\path\\to\\photo.jpg
    .venv\\Scripts\\python.exe -m validation.preview_local --all-metadata photo.jpg
"""

import argparse
import sys
from pathlib import Path

from metatracer.db.models import RawMetadataItem
from metatracer.detectors.registry import DetectorRegistry
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from metatracer.extractors.sniff import SNIFF_HEADER_BYTES, AssetKind, sniff_asset_kind

_EXTRACTORS = {
    AssetKind.pdf: PdfMetadataExtractor,
    AssetKind.image: ImageMetadataExtractor,
}


def preview_file(path: Path, *, show_all_metadata: bool) -> bool:
    """Print the findings (and optionally all metadata) of one local file.

    Returns True when the file was processed (findings or not), False on
    unsupported type or extraction failure. Never raises on a bad file:
    one broken file must not abort the preview of the rest.
    """
    print(f"\n=== {path.name} ===")
    if not path.is_file():
        print("  not a file — skipped")
        return False
    header = path.read_bytes()[:SNIFF_HEADER_BYTES]
    kind = sniff_asset_kind(header)
    if kind is None:
        print("  unsupported type (not PDF/JPEG/PNG/TIFF/WebP) — skipped")
        return False
    try:
        fields = _EXTRACTORS[kind]().extract(path)
    except Exception as exc:
        print(f"  extraction failed: {type(exc).__name__}: {exc}")
        return False

    items = [
        RawMetadataItem(asset_id=path.name, namespace=f.namespace, key=f.key, value=f.value)
        for f in fields
    ]
    drafts = DetectorRegistry().detect_all(items)

    print(f"  {len(items)} metadata fields extracted ({kind.value})")
    if drafts:
        print(f"  {len(drafts)} finding(s) the scan would report:")
        for draft in drafts:
            print(
                f"    [{draft.finding_type.value}] ({draft.confidence.value}) "
                f"{draft.field_source}: {draft.evidence_snippet}"
            )
    else:
        print("  no findings — detectors would stay silent on this file")

    if show_all_metadata:
        print("  --- all extracted metadata ---")
        for item in items:
            print(f"    {item.namespace}:{item.key} = {item.value}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", type=Path, nargs="+", help="local files to preview")
    parser.add_argument(
        "--all-metadata",
        action="store_true",
        help="also dump every extracted metadata field, not just the findings",
    )
    args = parser.parse_args()

    print(
        "PRIVACY GATE: anything shown below WILL be public if you upload the "
        "file.\nOnly publish files whose metadata you accept exposing."
    )
    processed = sum(preview_file(p, show_all_metadata=args.all_metadata) for p in args.files)
    print(f"\n{processed}/{len(args.files)} file(s) processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
