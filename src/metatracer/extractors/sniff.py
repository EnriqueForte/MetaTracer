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

from metatracer.extractors.targets import DOCUMENT_EXTENSIONS, OFFICE_EXTENSIONS

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
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_OFFICE_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-word.document.macroenabled.12",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.ms-powerpoint.presentation.macroenabled.12",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
    }
)


class AssetKind(StrEnum):
    """Document families the extractors support."""

    pdf = "pdf"
    image = "image"
    html = "html"
    javascript = "javascript"
    office = "office"


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


# Declared types for which an extensionless URL is worth a GET. HTML is
# deliberately absent: a nav link is not a document, and downloading every
# in-scope page would turn the depth-1 crawl into a site mirror. Empty and
# ``octet-stream`` stay, because the magic bytes are the real decision.
_FETCHABLE_DECLARED_TYPES = frozenset(
    {
        "application/pdf",
        "application/octet-stream",
        "binary/octet-stream",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/tiff",
        "image/webp",
        "application/javascript",
        "text/javascript",
        "application/ecmascript",
        "text/ecmascript",
    }
    | _OFFICE_CONTENT_TYPES
)


def worth_fetching(content_type: str | None) -> bool:
    """True when a HEAD response's type justifies downloading the body.

    ``None`` and an empty type are accepted: the body is classified by magic
    bytes. ``text/html`` is rejected here so extensionless page links are not
    fetched as documents.
    """
    if content_type is None:
        return True
    base = content_type.split(";", 1)[0].strip().lower()
    if not base:
        return True
    return base in _FETCHABLE_DECLARED_TYPES


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
    # A ZIP is an office document only when the URL or the declared type says
    # so. A random archive is not parsed. A .docx that is not a ZIP falls
    # through to the document-extension rejection below.
    content = content_type.split(";", 1)[0].strip().lower()
    if header.startswith(_ZIP_MAGIC) and (
        path.endswith(OFFICE_EXTENSIONS) or content in _OFFICE_CONTENT_TYPES
    ):
        return AssetKind.office
    if path.endswith(DOCUMENT_EXTENSIONS):
        return None
    # A .js URL is never recycled as HTML (error pages with text/html).
    if path.endswith(_JS_PATH_SUFFIXES):
        return AssetKind.javascript if _looks_like_text(header) else None
    if content in _HTML_CONTENT_TYPES or path.endswith(_HTML_PATH_SUFFIXES):
        return AssetKind.html
    if content in _JS_CONTENT_TYPES:
        return AssetKind.javascript if _looks_like_text(header) else None
    return None


def _looks_like_text(header: bytes) -> bool:
    """Reject obviously-binary buffers (NUL in the sniff window)."""
    return b"\x00" not in header[:SNIFF_HEADER_BYTES]
