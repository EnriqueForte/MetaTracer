"""Image metadata extraction: EXIF (incl. raw GPS), IPTC and XMP (TASK-01 subtask 1.4).

GPS values are persisted RAW: DMS rationals become JSON arrays of ``"num/den"``
strings (e.g. ``["40/1", "24/1", "4635/100"]``) and hemisphere refs are
normalized to single uppercase ``N``/``S``/``E``/``W`` letters. Conversion to
decimal WGS84 is the GpsDetector's job (TASK-02) — this extractor never alters
the evidence.

Blobs are never persisted: EXIF thumbnails, ICC profiles and raw APPn segments
are skipped by construction (only structured tag values are read), unknown
numeric EXIF tags are dropped (MakerNote-style binary payloads), and the
sanitizer refuses oversized byte values. A block a format does not support is
omitted without failing the asset.
"""

import logging
from pathlib import Path
from typing import Any

from PIL import Image, IptcImagePlugin
from PIL.ExifTags import GPSTAGS, TAGS

from metatracer.core.exceptions import ExtractionError
from metatracer.core.logging import sanitize_for_log
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value
from metatracer.extractors.xmp import parse_xmp_packet

# Pillow's decompression-bomb ceiling, set explicitly so a later Pillow
# release cannot raise it silently (TASK-32). About 179 megapixels.
Image.MAX_IMAGE_PIXELS = 178_956_970

logger = logging.getLogger("metatracer.extractors.image")

EXIF_NAMESPACE = "exif"
IPTC_NAMESPACE = "iptc"
XMP_NAMESPACE = "xmp"

_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825
_TIFF_XMP_TAG = 700

# Structural EXIF pointers and known binary payloads: not metadata evidence.
_SKIP_EXIF_TAGS = frozenset(
    {"ExifOffset", "GPSInfo", "InteroperabilityOffset", "MakerNote", "PrintImageMatching"}
)
_HEMISPHERE_REFS = frozenset({"N", "S", "E", "W"})
_GPS_REF_KEYS = frozenset({"GPSLatitudeRef", "GPSLongitudeRef"})

# IPTC IIM dataset names for the ApplicationRecord (record 2) fields we know.
_IPTC_NAMES = {
    (2, 5): "ObjectName",
    (2, 15): "Category",
    (2, 20): "SupplementalCategories",
    (2, 25): "Keywords",
    (2, 40): "SpecialInstructions",
    (2, 55): "DateCreated",
    (2, 60): "TimeCreated",
    (2, 80): "Byline",
    (2, 85): "BylineTitle",
    (2, 90): "City",
    (2, 92): "SubLocation",
    (2, 95): "ProvinceState",
    (2, 100): "CountryCode",
    (2, 101): "CountryName",
    (2, 103): "OriginalTransmissionReference",
    (2, 105): "Headline",
    (2, 110): "Credit",
    (2, 115): "Source",
    (2, 116): "CopyrightNotice",
    (2, 118): "Contact",
    (2, 120): "CaptionAbstract",
    (2, 122): "WriterEditor",
}


class ImageMetadataExtractor:
    """Extracts EXIF/IPTC/XMP fields from an image on disk."""

    def extract(self, path: Path) -> list[ExtractedField]:
        """Return the metadata fields of the image; raise ExtractionError on failure."""
        try:
            with Image.open(path) as img:
                try:
                    # Ensures late chunks (post-IDAT iTXt in PNGs) are read; the
                    # decompression-bomb guard aborts absurd dimensions.
                    img.load()
                except Exception as exc:
                    raise ExtractionError(
                        f"cannot decode image: {type(exc).__name__}: {sanitize_for_log(exc)}"
                    ) from exc
                return self._exif_fields(img) + self._iptc_fields(img) + self._xmp_fields(img)
        except ExtractionError:
            raise
        except Exception as exc:
            # UnidentifiedImageError, OSError, SyntaxError, ValueError...: all mean
            # 'this asset is not parseable'; the pipeline marks it and moves on.
            raise ExtractionError(
                f"cannot parse image: {type(exc).__name__}: {sanitize_for_log(exc)}"
            ) from exc

    def _exif_fields(self, img: Image.Image) -> list[ExtractedField]:
        try:
            exif = img.getexif()
        except Exception as exc:
            logger.warning("EXIF block unreadable: %s", sanitize_for_log(exc))
            return []
        named: dict[str, Any] = {}
        for tag_id, value in exif.items():  # IFD0
            self._collect_tag(named, TAGS.get(tag_id), value)
        for ifd in (_EXIF_IFD, _GPS_IFD):
            try:
                sub = exif.get_ifd(ifd)
            except Exception as exc:
                logger.warning("EXIF sub-IFD %#x unreadable: %s", ifd, sanitize_for_log(exc))
                continue
            tags = GPSTAGS if ifd == _GPS_IFD else TAGS
            for tag_id, value in sub.items():
                self._collect_tag(named, tags.get(tag_id), value)
        fields: list[ExtractedField] = []
        for key, value in named.items():
            if key in _GPS_REF_KEYS:
                value = _normalize_hemisphere_ref(value)
            sanitized = sanitize_value(value)
            if sanitized and sanitized.strip():
                fields.append(ExtractedField(EXIF_NAMESPACE, key, sanitized))
        return fields

    @staticmethod
    def _collect_tag(named: dict[str, Any], name: str | None, value: Any) -> None:
        """Keep only known tag names; unknown numeric tags may be binary blobs."""
        if name is None or name in _SKIP_EXIF_TAGS:
            return
        named[name] = value

    def _iptc_fields(self, img: Image.Image) -> list[ExtractedField]:
        try:
            iptc = IptcImagePlugin.getiptcinfo(img)
        except Exception as exc:
            logger.warning("IPTC block unreadable: %s", sanitize_for_log(exc))
            return []
        if not iptc:
            return []
        fields: list[ExtractedField] = []
        for (record, dataset), value in iptc.items():
            key = _IPTC_NAMES.get((record, dataset), f"{record}:{dataset}")
            sanitized = sanitize_value(value)
            if sanitized and sanitized.strip():
                fields.append(ExtractedField(IPTC_NAMESPACE, key, sanitized))
        return fields

    def _xmp_fields(self, img: Image.Image) -> list[ExtractedField]:
        packet = _xmp_packet(img)
        if not packet:
            return []
        return [
            ExtractedField(XMP_NAMESPACE, key, value)
            for key, value in parse_xmp_packet(packet).items()
        ]


def _normalize_hemisphere_ref(value: Any) -> str:
    """Normalize a GPS hemisphere ref to a single uppercase N/S/E/W letter."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip().upper()
    return text if text in _HEMISPHERE_REFS else str(value)


def _xmp_packet(img: Image.Image) -> bytes | str | None:
    """Locate the raw XMP packet across JPEG APP1, PNG iTXt and TIFF tag 700."""
    for key in ("xmp", "XML:com.adobe.xmp"):
        raw = img.info.get(key)
        if raw:
            return raw
    tag_v2 = getattr(img, "tag_v2", None)  # TIFF
    if tag_v2 is not None:
        try:
            raw = tag_v2.get(_TIFF_XMP_TAG)
        except Exception:
            raw = None
        if raw:
            return raw
    return None
