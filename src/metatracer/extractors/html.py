"""HTML page metadata extraction (TASK-09, subtask 9.3).

Persists title, a small set of meta tags and HTML comments — never the page
body. Inline ``<script>`` comments are delegated to the JS extractor so a
single HTML asset can carry both ``html:*`` and ``js:comment`` rows.
"""

from bs4 import BeautifulSoup, Comment

from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.javascript import JavaScriptMetadataExtractor
from metatracer.extractors.sanitize import sanitize_value

HTML_NAMESPACE = "html"
# Hard cap so a comment-stuffed 5 MB page cannot explode RawMetadataItem rows.
MAX_HTML_COMMENTS = 32

_META_NAMES = frozenset(
    {"author", "generator", "description", "keywords", "application-name", "creator"}
)


class HtmlMetadataExtractor:
    """Extracts structured fields from an HTML document body."""

    def extract(self, source: bytes | str) -> list[ExtractedField]:
        raw = source if isinstance(source, bytes) else source.encode("utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")
        fields: list[ExtractedField] = []
        title = soup.title.string if soup.title else None
        if title:
            value = sanitize_value(str(title).strip())
            if value:
                fields.append(ExtractedField(namespace=HTML_NAMESPACE, key="title", value=value))
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "")
            if not isinstance(name, str):
                continue
            name = name.strip().lower()
            if name not in _META_NAMES:
                continue
            content = tag.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            value = sanitize_value(content.strip())
            if value:
                fields.append(
                    ExtractedField(namespace=HTML_NAMESPACE, key=f"meta:{name}", value=value)
                )
        comment_count = 0
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            if comment_count >= MAX_HTML_COMMENTS:
                break
            text = str(comment).strip()
            if not text or text.lower().startswith("[if"):
                continue
            value = sanitize_value(text)
            if value:
                fields.append(
                    ExtractedField(namespace=HTML_NAMESPACE, key="comment", value=value)
                )
                comment_count += 1
        js_extractor = JavaScriptMetadataExtractor()
        for script in soup.find_all("script"):
            if script.get("src"):
                continue  # external files are downloaded as their own assets
            body = script.string
            if not body or not str(body).strip():
                continue
            fields.extend(js_extractor.extract(str(body)))
        return fields
