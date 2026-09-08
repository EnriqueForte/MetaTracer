"""JavaScript comment extractor (TASK-09, subtask 9.4)."""

from metatracer.extractors.javascript import (
    MAX_JS_COMMENTS,
    JavaScriptMetadataExtractor,
    extract_js_comments,
)


def test_line_and_block_comments() -> None:
    source = """
    /* INTERNAL build leftover */
    function boot() {
      // FIXME: path C:\\\\Users\\\\web_admin\\\\app.js
      return 1;
    }
    """
    comments = extract_js_comments(source)
    assert "INTERNAL build leftover" in comments
    assert any("FIXME:" in item for item in comments)


def test_https_url_is_not_a_comment() -> None:
    source = 'const url = "https://target.com/app.js";\nconst x = 1;'
    assert extract_js_comments(source) == []


def test_extractor_persists_js_namespace() -> None:
    fields = JavaScriptMetadataExtractor().extract(b"/* TODO: strip */\n")
    assert len(fields) == 1
    assert fields[0].namespace == "js"
    assert fields[0].key == "comment"
    assert fields[0].value == "TODO: strip"
    assert "function" not in fields[0].value


def test_js_comment_cap() -> None:
    source = "\n".join(f"// TODO: n{i}" for i in range(40))
    fields = JavaScriptMetadataExtractor().extract(source)
    assert len(fields) == MAX_JS_COMMENTS
