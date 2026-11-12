import re
from pathlib import Path

import pytest

from planet.highlight import (
    CODE_BACKGROUND,
    highlight_blocks,
    highlight_code,
    language_label,
    palette,
    stylesheet,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("classes", "label"),
    [
        ("language-clojure", "clojure"),
        ("lang-cl", "common-lisp"),
        ("sourceCode haskell", "haskell"),
        ("highlight clojure", "clojure"),
        ("src src-emacs-lisp", "emacs-lisp"),
        ("brush: clojure; title: ; notranslate", "clojure"),
        ("clojure", "clojure"),
        ("language-edn", "clojure"),
        ("clojure-repl", "clojure"),
        ("language-ts", "typescript"),
        ("highlight", None),
        ("hljs line-numbers", None),
        ("language-mermaid", None),
    ],
)
def test_language_label(classes: str, label: str | None) -> None:
    assert language_label(classes) == label


def test_labelled_block_is_highlighted() -> None:
    out = highlight_blocks('<pre class="language-python"><code>def f(): pass</code></pre>')
    assert out.startswith('<pre class="code"><code class="language-python"><span class="k">def')


def test_label_on_code_element_is_used() -> None:
    out = highlight_blocks('<pre><code class="language-python">def f(): pass</code></pre>')
    assert 'class="language-python"' in out


def test_unlabelled_lisp_is_clojure() -> None:
    for code in ["(defn f [])", "; comment\n(f)", "[1 2]", "user=> (+ 1 2)\n3"]:
        assert 'class="language-clojure"' in highlight_code(code, None), code


def test_unlabelled_other_code_stays_plain() -> None:
    assert highlight_code("ls -la <dir>", None) == (
        '<pre class="code"><code>ls -la &lt;dir&gt;</code></pre>'
    )
    assert "<span" not in highlight_code("graph TD; A-->B", "mermaid")


def test_publisher_markup_is_replaced_and_breaks_become_newlines() -> None:
    out = highlight_blocks("<pre><span>(defn</span> f<br>  [])</pre>")
    assert '<span class="kd">defn </span>' in out
    assert '<span class="nv">f</span>\n<span class="w">  </span>' in out
    assert "<br" not in out


def test_code_text_stays_escaped() -> None:
    out = highlight_blocks('<pre class="language-html">&lt;script&gt;x()&lt;/script&gt;</pre>')
    assert "<script>" not in out
    assert "&lt;" in out


def test_surrounding_content_is_kept_and_no_pre_is_untouched() -> None:
    assert highlight_blocks("<p>a &amp; b</p>") == "<p>a &amp; b</p>"
    out = highlight_blocks("<p>before</p><pre>x</pre><p>after</p>")
    assert out.startswith("<p>before</p><pre") and out.endswith("<p>after</p>")


def test_empty_blocks_are_removed() -> None:
    out = highlight_blocks('<p>a</p><pre id="output"></pre><pre><code> \n</code></pre><p>b</p>')
    assert out == "<p>a</p><p>b</p>"
    assert highlight_blocks("<pre></pre>") == ""


def test_stylesheet_has_both_modes() -> None:
    css = stylesheet()
    light, dark = css.split("@media (prefers-color-scheme: dark)")
    assert "pre.code .k {" in light and "pre.code .k {" in dark
    assert "pre.code .ss {" in light  # Clojure keywords


def _luminance(hex_colour: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_token_colours_meet_wcag_aa(mode: str) -> None:
    background = CODE_BACKGROUND[mode]
    for token, style in palette(mode).items():
        for colour in re.findall(r"#[0-9a-fA-F]{6}", style):
            assert contrast(colour, background) >= 4.5, (mode, token, colour)


def _css_variables(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def test_page_colours_meet_wcag_aa_and_match_the_code_background() -> None:
    css = (ROOT / "static" / "css" / "style.css").read_text()
    root, rest = css.split("@media (prefers-color-scheme: dark)", 1)
    light = _css_variables(root)
    dark = light | _css_variables(rest.split("}", 2)[0] + "}")
    for mode, colours in (("light", light), ("dark", dark)):
        assert colours["code-bg"].lower() == CODE_BACKGROUND[mode], mode
        for fg, bg in [
            ("fg", "bg"), ("muted", "bg"), ("fg", "code-bg"), ("accent-fg", "accent"),
        ]:  # fmt: skip
            assert contrast(colours[fg], colours[bg]) >= 4.5, (mode, fg, bg)
