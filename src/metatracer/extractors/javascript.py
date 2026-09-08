"""JavaScript comment extraction (TASK-09, subtask 9.4).

Walks source text and collects ``//`` line comments and ``/* */`` block
comments while skipping string literals (so ``https://`` is not a comment).
The full source is never persisted — only sanitized comment text, namespace
``js``, key ``comment``.
"""

from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.sanitize import sanitize_value

JS_NAMESPACE = "js"
JS_COMMENT_KEY = "comment"
# Hard cap so a comment-stuffed 50 MB file cannot explode RawMetadataItem rows.
MAX_JS_COMMENTS = 32

_STRING_DELIMS = frozenset({"'", '"', "`"})


class JavaScriptMetadataExtractor:
    """Extracts comments from a JS source buffer."""

    def extract(self, source: bytes | str) -> list[ExtractedField]:
        text = source.decode("utf-8", errors="replace") if isinstance(source, bytes) else source
        fields: list[ExtractedField] = []
        for comment in extract_js_comments(text)[:MAX_JS_COMMENTS]:
            value = sanitize_value(comment)
            if not value:
                continue
            fields.append(
                ExtractedField(namespace=JS_NAMESPACE, key=JS_COMMENT_KEY, value=value)
            )
        return fields


def extract_js_comments(source: str) -> list[str]:
    """Return stripped JS comments; string literals are not scanned."""
    comments: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        char = source[i]
        if char in _STRING_DELIMS:
            i = _skip_string(source, i)
            continue
        if char == "/" and i + 1 < n:
            nxt = source[i + 1]
            if nxt == "/":
                end = source.find("\n", i + 2)
                if end == -1:
                    end = n
                comments.append(source[i + 2 : end])
                i = end
                continue
            if nxt == "*":
                end = source.find("*/", i + 2)
                if end == -1:
                    comments.append(source[i + 2 :])
                    break
                comments.append(source[i + 2 : end])
                i = end + 2
                continue
        i += 1
    return [item.strip() for item in comments if item.strip()]


def _skip_string(source: str, start: int) -> int:
    """Return the index just after the string that starts at ``start``."""
    delim = source[start]
    i = start + 1
    n = len(source)
    while i < n:
        char = source[i]
        if char == "\\":
            i += 2
            continue
        if char == delim:
            return i + 1
        # Template-literal interpolation: resume scanning after ``}``.
        if delim == "`" and char == "$" and i + 1 < n and source[i + 1] == "{":
            i = _skip_template_expr(source, i + 2)
            continue
        i += 1
    return n


def _skip_template_expr(source: str, start: int) -> int:
    """Skip ``${...}`` with nested braces; comments inside expressions are ignored."""
    depth = 1
    i = start
    n = len(source)
    while i < n and depth:
        char = source[i]
        if char in _STRING_DELIMS:
            i = _skip_string(source, i)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return i
