"""InternalPathDetector (TASK-02 subtask 2.3).

Covers Windows drive paths (``C:\\Users\\...``, also with ``/``), UNC shares
(``\\\\fileserver\\share\\...``), Unix/macOS homes and service roots
(``/home``, ``/Users``, ``/private/tmp``, ``/private/var``, ``/var/www``,
``/srv``, ``/root``), install roots (``C:\\Program Files``, ``C:\\ProgramData``),
``AppData`` that is not under ``Users``, and tilde homes (``~usuario/``).

Generic ``/opt`` and ``/usr`` stay unmatched. Those prefixes appear in vendor
install notes, man pages and library strings (``/usr/lib``, ``/opt/lampp``)
far more often than they name a person or an internal host, and the rubric
prefers under-detection over that noise.

Negatives: a match wrapped in a URL token (``http://``, ``https://``,
``file:///``, ``xmlns:``...) or a relative path (``./images/``) is not
internal-path evidence. The check is token-based: the whitespace-delimited
token containing the match must not contain ``://`` before the match nor a
leading ``.``.

Confidence (subtask 2.3.5): ``high`` for user-bound roots (``Users\\``,
``Documents and Settings``, UNC, ``/home``, ``/Users``, ``/root``); ``medium``
for the rest (``C:\\Windows``, ``inetpub``, ``xampp``, ``Program Files``,
``ProgramData``, ``AppData`` outside ``Users``, ``~usuario/``,
``/private/tmp``, ``/private/var``, ``/srv`` and any ``/var/www/...``).
A deploy or install root carries no user name.
"""

import re
from collections.abc import Sequence

from metatracer.db.models import Confidence, FindingType, RawMetadataItem
from metatracer.detectors.base import FindingDraft, collapse_whitespace, normalize_text

_WINDOWS_DRIVE_RE = re.compile(
    r"[A-Za-z]:[\\/](?:Users|Documents and Settings|Windows|inetpub|xampp|"
    r"Program Files|ProgramData)[\\/][^\s\"<>|]+",
    re.IGNORECASE,
)
# AppData that is not the first segment under Users (that case is already a
# high-confidence user path). ``C:\Temp\AppData\...`` and ``C:\AppData\...``.
_WINDOWS_APPDATA_RE = re.compile(
    r"[A-Za-z]:[\\/](?![Uu]sers[\\/])(?:[^\\/\s]+[\\/])*AppData[\\/][^\s\"<>|]+",
    re.IGNORECASE,
)
_TILDE_HOME_RE = re.compile(r"(?<![A-Za-z0-9])~[A-Za-z0-9._-]{1,32}/[^\s\"<>|]+")
_UNC_RE = re.compile(r"\\\\[A-Za-z0-9_.\-]+\\[A-Za-z0-9_$.\-]+(?:\\[^\s\"<>|]+)*")
# The lookbehind keeps the Unix roots from matching inside a Windows drive
# path ("C:/Users/..."), a URL ("target.com/home/...") or a longer relative
# path ("./images/home/..."): the root must start at a token-ish boundary.
_UNIX_RE = re.compile(
    r"(?<![A-Za-z0-9_:.\-/])(?:/home|/Users|/private/tmp|/private/var|"
    r"/var/www|/srv|/root)/[^\s\"<>|]+",
    re.IGNORECASE,
)

# Sentence punctuation clinging to a path inside prose is not part of the path.
_TRAILING_CHARS = ".,;:!?)]}'\""

# XML namespace declarations may carry path-like URIs after the colon
# ("xmlns:x=/home/..."); a token whose prefix declares a namespace is never
# filesystem evidence (subtask 2.3.4).
_XMLNS_PREFIX_RE = re.compile(r"xmlns(?::[A-Za-z0-9_.\-]*)?=?[\"']?$", re.IGNORECASE)

_HIGH_UNIX_PREFIXES = ("/home/", "/users/", "/root/")
# Deploy roots without a user name: /var/www/<anything> included. The contract
# (2.3.5) reserves ``high`` for user-bound roots and UNC; the classifier applies
# the matching ceiling (``/var/www`` without user -> medium).
_MEDIUM_UNIX_PREFIXES = ("/private/tmp/", "/private/var/", "/srv/", "/var/www/")


class InternalPathDetector:
    """Detects filesystem/UNC paths leaked into metadata values."""

    finding_type = FindingType.internal_path

    def detect(self, items: Sequence[RawMetadataItem]) -> list[FindingDraft]:
        drafts: list[FindingDraft] = []
        for item in items:
            text = collapse_whitespace(normalize_text(item.value))
            if not text:
                continue
            seen_in_field: set[str] = set()
            for match in _iter_matches(text):
                path = match.group(0).rstrip(_TRAILING_CHARS)
                if not path or path.lower() in seen_in_field:
                    continue
                if _is_negative(text, match.start()):
                    continue
                seen_in_field.add(path.lower())
                drafts.append(
                    FindingDraft(
                        finding_type=FindingType.internal_path,
                        field_source=f"{item.namespace}:{item.key}",
                        evidence_snippet=path,
                        confidence=_confidence_for(path),
                    )
                )
        return drafts


def _iter_matches(text: str) -> list[re.Match[str]]:
    """All candidate path matches, Windows/UNC first (they cannot overlap Unix)."""
    return [
        *re.finditer(_WINDOWS_DRIVE_RE, text),
        *re.finditer(_WINDOWS_APPDATA_RE, text),
        *re.finditer(_UNC_RE, text),
        *re.finditer(_UNIX_RE, text),
        *re.finditer(_TILDE_HOME_RE, text),
    ]


def _is_negative(text: str, match_start: int) -> bool:
    """True when the match lives inside a URL token, an ``xmlns`` declaration
    or a relative path."""
    token_start = text.rfind(" ", 0, match_start) + 1  # text is whitespace-collapsed
    prefix = text[token_start:match_start]
    if "://" in prefix or prefix.startswith("."):
        return True
    return _XMLNS_PREFIX_RE.search(prefix) is not None


def _confidence_for(path: str) -> Confidence:
    low = path.lower()
    if low.startswith("\\\\"):  # UNC share
        return Confidence.high
    if re.match(r"[a-z]:", low):  # Windows drive
        if re.match(r"[a-z]:[\\/](users|documents and settings)[\\/]", low):
            return Confidence.high
        return Confidence.medium  # C:\Windows, inetpub, xampp
    if low.startswith(_HIGH_UNIX_PREFIXES):
        return Confidence.high
    if low.startswith(_MEDIUM_UNIX_PREFIXES):
        return Confidence.medium
    return Confidence.medium
