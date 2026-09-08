"""Magic-byte allowlist for downloaded bodies (TASK-01 subtask 1.2.4).

Neither the URL extension nor the Content-Type header is trusted on its own:
the decision to parse a body as PDF or image is taken from the leading bytes.
Anything that does not match a known signature becomes
``skipped``/``unsupported_type`` — HTML downloaded by mistake is never parsed
as a document. The contracted acceptable Content-Types (``application/pdf``,
``image/jpeg``, ``image/png``, ``image/tiff``, ``image/webp`` and
``application/octet-stream`` only when the magic bytes match) are recorded on
the asset for traceability; the magic bytes decide.

TASK-09 adds HTML and JavaScript as first-class kinds, but a URL that *claims*
to be a document (``.pdf`` / image extension) and fails the magic-byte check
stays ``unsupported_type``. Error pages must not be recycled as HTML assets.
"""

from enum import StrEnum
from urllib.parse import urlsplit

from metatracer.extractors.targets import DOCUMENT_EXTENSIONS

# Leading bytes needed to decide every signature below (RIFF....WEBP is the
# longest lookahead: 12 bytes).
SNIFF_HEADER_BYTES = 16

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_JS_CONTENT_TYPES = frozenset(
    {
        "application/javascript",
        "text/javascript",
        "application/ecmascript",
        "text/ecmascript",
    }
)
_HTML_PATH_SUFFIXES = (".html", ".htm")
_JS_PATH_SUFFIXES = (".js",)


class AssetKind(StrEnum):
    """Document families the extractors support."""

    pdf = "pdf"
    image = "image"
    html = "html"
    javascript = "javascript"


def sniff_asset_kind(header: bytes) -> AssetKind | None:
    """Return the document kind these leading bytes represent, or None.

    Magic-byte only: PDF and images. HTML/JS have no reliable signature and
    are classified by :func:`classify_downloaded_asset`.
    """
    if header.startswith(b"%PDF"):
        return AssetKind.pdf
    if header.startswith(b"\xff\xd8\xff"):  # JPEG: SOI + first marker
        return AssetKind.image
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return AssetKind.image
    if header[:4] in (b"II*\x00", b"MM\x00*"):  # TIFF little/big endian
        return AssetKind.image
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return AssetKind.image
    return None


def classify_downloaded_asset(
    header: bytes,
    *,
    content_type: str = "",
    url: str = "",
) -> AssetKind | None:
    """Decide the extractor family for a downloaded body.

    Magic bytes win. A document-extension URL that is not PDF/image is
    unsupported — even if the body looks like HTML. HTML and JS are accepted
    from content-type and/or path on non-document URLs.
    """
    magic = sniff_asset_kind(header)
    if magic is not None:
        return magic
    path = urlsplit(url).path.lower()
    if path.endswith(DOCUMENT_EXTENSIONS):
        return None
    # A .js URL is never recycled as HTML (error pages with text/html).
    if path.endswith(_JS_PATH_SUFFIXES):
        return AssetKind.javascript if _looks_like_text(header) else None
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct in _HTML_CONTENT_TYPES or path.endswith(_HTML_PATH_SUFFIXES):
        return AssetKind.html
    if ct in _JS_CONTENT_TYPES:
        return AssetKind.javascript if _looks_like_text(header) else None
    return None


def _looks_like_text(header: bytes) -> bool:
    """Reject obviously-binary buffers (NUL in the sniff window)."""
    return b"\x00" not in header[:SNIFF_HEADER_BYTES]
