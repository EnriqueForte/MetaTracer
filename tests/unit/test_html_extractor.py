"""HtmlMetadataExtractor (TASK-09, subtask 9.3)."""

from metatracer.extractors.html import HtmlMetadataExtractor
from metatracer.extractors.sniff import AssetKind, classify_downloaded_asset, sniff_asset_kind


def _by_key(fields) -> dict[tuple[str, str], str]:
    return {(field.namespace, field.key): field.value for field in fields}


def test_title_meta_and_comments_extracted() -> None:
    html = b"""<!doctype html>
<html>
<head>
  <title>About ACME</title>
  <meta name="generator" content="WordPress 6.4.2">
  <meta name="author" content="recon@acme-corp.test">
  <meta name="description" content="Public marketing page">
</head>
<body>
  <!-- TODO: remove staging credentials -->
  <p>hello</p>
</body>
</html>
"""
    fields = HtmlMetadataExtractor().extract(html)
    by_key = _by_key(fields)
    assert by_key[("html", "title")] == "About ACME"
    assert by_key[("html", "meta:generator")] == "WordPress 6.4.2"
    assert by_key[("html", "meta:author")] == "recon@acme-corp.test"
    assert by_key[("html", "meta:description")] == "Public marketing page"
    assert by_key[("html", "comment")] == "TODO: remove staging credentials"
    assert all("<html" not in field.value for field in fields)
    assert all("<!doctype" not in field.value.lower() for field in fields)


def test_conditional_and_empty_comments_skipped() -> None:
    html = b"""<html><body>
    <!--[if IE]>old ie<![endif]-->
    <!--   -->
    <!-- keep me -->
    </body></html>"""
    fields = HtmlMetadataExtractor().extract(html)
    comments = [field.value for field in fields if field.key == "comment"]
    assert comments == ["keep me"]


def test_inline_script_comments_become_js_namespace() -> None:
    html = b"""<html><body>
    <script>/* FIXME: leftover */ var x = 1;</script>
    <script src="/app.js"></script>
    </body></html>"""
    fields = HtmlMetadataExtractor().extract(html)
    js = [field for field in fields if field.namespace == "js"]
    assert len(js) == 1
    assert js[0].key == "comment"
    assert "FIXME: leftover" in js[0].value


def test_document_url_with_html_body_is_unsupported() -> None:
    header = b"<html><body>not a pdf</body></html>"
    assert sniff_asset_kind(header) is None
    assert (
        classify_downloaded_asset(
            header, content_type="application/pdf", url="http://target.com/fake.pdf"
        )
        is None
    )


def test_html_and_js_urls_classify_without_magic_bytes() -> None:
    html = b"<!doctype html><html></html>"
    assert (
        classify_downloaded_asset(html, content_type="text/html", url="http://target.com/")
        is AssetKind.html
    )
    js = b"function boot() { return 1; }"
    assert (
        classify_downloaded_asset(
            js, content_type="application/javascript", url="http://target.com/app.js"
        )
        is AssetKind.javascript
    )


def test_js_url_with_html_content_type_is_still_javascript() -> None:
    body = b"<html><body>not javascript</body></html>"
    assert (
        classify_downloaded_asset(
            body, content_type="text/html", url="http://target.com/app.js"
        )
        is AssetKind.javascript
    )


def test_html_page_with_inline_svg_stays_html() -> None:
    html = b"<!doctype html><html><body><svg xmlns='http://www.w3.org/2000/svg'></svg></body></html>"
    assert (
        classify_downloaded_asset(html, content_type="text/html", url="http://target.com/")
        is AssetKind.html
    )


def test_html_comment_cap() -> None:
    comments = "".join(f"<!-- TODO: n{i} -->" for i in range(40))
    html = f"<html><body>{comments}</body></html>".encode()
    fields = HtmlMetadataExtractor().extract(html)
    assert len([field for field in fields if field.key == "comment"]) == 32
