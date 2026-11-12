import pytest

from planet.model import Entry
from planet.sanitize import clean_html, plain_text, sanitize_entry


def test_removes_script_handlers_and_javascript_urls() -> None:
    out = clean_html(
        '<p onclick="x()">hi</p><script>alert(1)</script>'
        '<a href="javascript:alert(2)">a</a><iframe src="https://e.x"></iframe>'
    )
    assert "script" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert "iframe" not in out
    assert "<p>hi</p>" in out


def test_keeps_ordinary_formatting() -> None:
    html = '<pre><code>(defn f [])</code></pre><img src="https://e.x/i.png" alt="a">'
    out = clean_html(html)
    assert "<pre><code>(defn f [])</code></pre>" in out
    assert 'src="https://e.x/i.png"' in out


def test_links_get_rel() -> None:
    assert 'rel="noopener noreferrer nofollow"' in clean_html('<a href="https://e.x">e</a>')


def test_code_blocks_keep_only_a_normalised_language_label() -> None:
    cleaned = clean_html(
        '<pre class="brush: clojure; notranslate" style="x"><code class="hljs">'
        '<span class="k" style="color:red">(defn</span></code></pre>'
        '<p class="language-clojure">p</p><code class="lang-js">x</code>'
    )
    assert cleaned == (
        '<pre class="language-clojure"><code><span>(defn</span></code></pre>'
        '<p>p</p><code class="language-javascript">x</code>'
    )


@pytest.mark.parametrize("tag", ["iframe", "noscript", "noembed", "NOFRAMES"])
def test_fallback_markup_inside_raw_text_elements_is_kept(tag: str) -> None:
    fragment = f'<p>a</p><{tag} src="x"><a href="https://e.x/">link</a></{tag}><p>b</p>'
    assert clean_html(fragment) == (
        '<p>a</p><a href="https://e.x/" rel="noopener noreferrer nofollow">link</a><p>b</p>'
    )


def test_plain_text() -> None:
    assert plain_text("Tips &amp; <b>tricks</b>") == "Tips & tricks"


def test_sanitize_entry() -> None:
    e = sanitize_entry(
        Entry(
            entry_id="i",
            title="<i>T</i>",
            link=None,
            content="<script>x</script><p>ok</p>",
            summary='<p onclick="x()">s</p>',
        )
    )
    assert e.title == "T"
    assert e.content == "<p>ok</p>"
    assert e.summary == "<p>s</p>"  # sanitized, kept for filters
