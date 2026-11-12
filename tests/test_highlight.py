import math
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
from planet.tailwind import COLOURS

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


_OKLCH = re.compile(r"oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)")


def _luminance(oklch: str) -> float:
    """WCAG relative luminance of an oklch colour, clipped to sRGB."""
    match = _OKLCH.fullmatch(oklch)
    assert match, oklch
    lightness, chroma, hue = (float(g) for g in match.groups())
    lightness /= 100
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    r, g, b = (min(1.0, max(0.0, c)) for c in linear)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_luminance_matches_known_colours() -> None:
    assert _luminance("oklch(100% 0 0)") == pytest.approx(1.0, abs=1e-4)
    assert _luminance("oklch(0% 0 0)") == pytest.approx(0.0, abs=1e-6)
    assert contrast("oklch(100% 0 0)", "oklch(0% 0 0)") == pytest.approx(21.0, abs=0.01)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_token_colours_meet_wcag_aa(mode: str) -> None:
    background = COLOURS[CODE_BACKGROUND[mode]]
    for token, ink in palette(mode).items():
        if ink.colour:
            assert contrast(COLOURS[ink.colour], background) >= 4.5, (mode, token, ink)


def test_stylesheet_uses_tailwind_colours() -> None:
    css = stylesheet()
    assert "#" not in css
    used = set(re.findall(r"oklch\([^)]*\)", css))
    assert used and used <= set(COLOURS.values())
    assert (
        "pre.code .ss { color: oklch(42.4% 0.199 265.638) } /* Literal.String.Symbol, blue-800 */"
        in css
    )
    assert "pre.code .kc { color: oklch(47% 0.157 37.304); font-weight: bold }" in css  # own ink
    assert "pre.code .kd { color: oklch(45.9% 0.187 3.815); font-weight: bold }" in css  # inherited


# `--name: oklch(...); /* tailwind-name ... */`
_CSS_COLOUR = re.compile(r"--([\w-]+):\s*(oklch\([^)]*\));\s*/\*\s*([a-z]+-\d+)")


def _css_variables(block: str) -> dict[str, str]:
    colours: dict[str, str] = {}
    for name, value, tailwind_name in _CSS_COLOUR.findall(block):
        assert COLOURS[tailwind_name] == value, (name, tailwind_name)
        colours[name] = value
    return colours


def test_page_colours_meet_wcag_aa_and_match_the_code_background() -> None:
    css = (ROOT / "static" / "css" / "style.css").read_text()
    assert not re.search(r":\s*#[0-9a-fA-F]{3,8}\b", css), "colours are Tailwind oklch values"
    root, rest = css.split("@media (prefers-color-scheme: dark)", 1)
    light = _css_variables(root)
    dark = light | _css_variables(rest.split("}", 2)[0] + "}")
    for mode, colours in (("light", light), ("dark", dark)):
        assert colours["code-bg"] == COLOURS[CODE_BACKGROUND[mode]], mode
        for fg, bg in [
            ("fg", "bg"), ("muted", "bg"), ("fg", "code-bg"), ("accent-fg", "accent"),
        ]:  # fmt: skip
            assert contrast(colours[fg], colours[bg]) >= 4.5, (mode, fg, bg)
