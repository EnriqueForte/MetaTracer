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
# Mutual recursion between strings and ${...} is capped so a hostile file
# cannot raise RecursionError (TASK-32). Past the cap the rest of the buffer
# is skipped and extraction still returns.
_MAX_SKIP_DEPTH = 64


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


def _skip_string(source: str, start: int, depth: int = 0) -> int:
    """Return the index just after the string that starts at ``start``."""
    if depth > _MAX_SKIP_DEPTH:
        return len(source)
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
            if depth >= _MAX_SKIP_DEPTH:
                return n
            i = _skip_template_expr(source, i + 2, depth + 1)
            continue
        i += 1
    return n


def _skip_template_expr(source: str, start: int, depth: int = 0) -> int:
    """Skip ``${...}`` with nested braces; comments inside expressions are ignored."""
    if depth > _MAX_SKIP_DEPTH:
        return len(source)
    brace_depth = 1
    i = start
    n = len(source)
    while i < n and brace_depth:
        char = source[i]
        if char in _STRING_DELIMS:
            if depth >= _MAX_SKIP_DEPTH:
                return n
            i = _skip_string(source, i, depth + 1)
            continue
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        i += 1
    return i
