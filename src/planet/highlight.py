"""Syntax highlighting for code blocks in entry content, done at render time.

Publishers label code in many ways (`language-clojure`, `lang-cl`,
`sourceCode haskell`, `highlight clojure`, `src-clojure`, `brush: clojure;`,
a bare `clojure`), and many ship their own highlighting markup. The
sanitizer keeps only the label, normalised to `language-<alias>` by
`language_label`; `highlight_blocks` then re-highlights each `<pre>` from
its plain text, so every post uses our colours in both light and dark mode.

Unlabelled code that starts like Lisp is highlighted as Clojure (this is
Planet Clojure); anything else unlabelled stays plain. Pygments' guessing is
too unreliable to use.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from functools import cache
from typing import cast

from pygments import highlight, lexers
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer
from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    String,
    Token,
    _TokenType,  # pyright: ignore[reportPrivateUsage]
)
from pygments.util import ClassNotFound
from selectolax.lexbor import LexborHTMLParser, LexborNode

# Class on every highlighted <pre>; the stylesheet scopes token colours to it.
BLOCK_CLASS = "code"
DEFAULT_LISP = "clojure"

_PREFIXES = ("language-", "lang-", "src-", "brush:")
# Labels Pygments doesn't know, mapped to ones it does.
_ALIASES = {"edn": "clojure", "plaintext": "text", "nohighlight": "text", "none": "text"}
_LANGUAGE_CLASS = re.compile(r"\blanguage-([\w+#.-]+)")
# `(`, `;` or `[` first, or a REPL prompt such as `user=>`.
_LOOKS_LIKE_LISP = re.compile(r"\A\s*(?:[(;\[]|[\w.-]*=>)")

# The stubs leave **options untyped.
_get_lexer = cast("Callable[..., Lexer]", lexers.get_lexer_by_name)  # pyright: ignore[reportUnknownMemberType]


@cache
def _known(name: str) -> str | None:
    """Pygments' canonical alias for a language name, or None."""
    name = _ALIASES.get(name, name)
    try:
        return _get_lexer(name).aliases[0]
    except ClassNotFound:
        return None


def language_label(class_value: str) -> str | None:
    """The first class token naming a language Pygments knows."""
    for token in class_value.replace(";", " ").lower().split():
        for prefix in _PREFIXES:
            token = token.removeprefix(prefix)
        token = token.removesuffix("-repl")
        if token and (alias := _known(token)):
            return alias
    return None


def _label_of(pre: LexborNode) -> str | None:
    for node in (pre, pre.css_first("code")):
        if node is not None and (m := _LANGUAGE_CLASS.search(node.attributes.get("class") or "")):
            return m.group(1)
    return None


@cache
def _lexer(alias: str) -> Lexer:
    return _get_lexer(alias, stripnl=False, ensurenl=False)


def _formatter() -> HtmlFormatter[str]:
    return HtmlFormatter(nowrap=True)


def highlight_code(text: str, language: str | None) -> str:
    """One <pre> block: highlighted when the language is known, else escaped."""
    if language is None and _LOOKS_LIKE_LISP.match(text):
        language = DEFAULT_LISP
    alias = _known(language) if language else None
    if alias and alias != "text":
        body = highlight(text, _lexer(alias), _formatter()).rstrip("\n")
        label = f' class="language-{alias}"'
    else:
        body, label = html.escape(text, quote=False), ""
    return f'<pre class="{BLOCK_CLASS}"><code{label}>{body}</code></pre>'


def highlight_blocks(fragment: str) -> str:
    """Re-highlight every <pre> in a sanitized HTML fragment.

    Blocks without text are removed: they are placeholders that the post's
    own scripts fill in, and scripts never survive sanitizing."""
    if "<pre" not in fragment:
        return fragment
    tree = LexborHTMLParser(fragment)
    for pre in tree.css("pre"):
        for br in pre.css("br"):
            br.replace_with("\n")
        text = (pre.text(deep=True) or "").strip("\n")
        if not text.strip():
            pre.decompose()
            continue
        block = LexborHTMLParser(highlight_code(text, _label_of(pre))).css_first("pre")
        if block is not None:
            pre.replace_with(block)
    body = tree.body
    return (body.inner_html or "") if body is not None else fragment


# Token colours. Few colours, all at least WCAG AA (4.5:1) against the code
# background of their mode (tests check this); structure comes from weight.
CODE_BACKGROUND = {"light": "#f0f0eb", "dark": "#1c1c1c"}

_PALETTE: dict[str, dict[_TokenType, str]] = {
    "light": {
        Comment: "italic #5c5c5c",
        Keyword: "bold #8c1061",
        Name.Builtin: "#5b2bb5",
        Name.Function: "bold",
        String: "#11632a",
        String.Symbol: "#0a4fa8",  # Clojure keywords, :like-this
        Number: "#8a3a00",
        Literal: "#8a3a00",
        Keyword.Constant: "bold #8a3a00",
        Operator.Word: "bold #8c1061",
        Generic.Prompt: "bold #5c5c5c",
        Generic.Output: "#5c5c5c",
        Error: "#b00020",
    },
    "dark": {
        Comment: "italic #a3a3a3",
        Keyword: "bold #f5a6d6",
        Name.Builtin: "#c9b0ff",
        Name.Function: "bold",
        String: "#a2e3a8",
        String.Symbol: "#93c5ff",
        Number: "#ffb878",
        Literal: "#ffb878",
        Keyword.Constant: "bold #ffb878",
        Operator.Word: "bold #f5a6d6",
        Generic.Prompt: "bold #a3a3a3",
        Generic.Output: "#a3a3a3",
        Error: "#ff8a8a",
    },
}


def _style(mode: str) -> type[Style]:
    return type(
        f"{mode.title()}Code",
        (Style,),
        {"background_color": CODE_BACKGROUND[mode], "styles": {Token: "", **_PALETTE[mode]}},
    )


def palette(mode: str) -> dict[_TokenType, str]:
    return _PALETTE[mode]


def _token_rules(mode: str, scope: str) -> list[str]:
    formatter: HtmlFormatter[str] = HtmlFormatter(style=_style(mode))
    # Untyped in the stubs: returns one CSS rule per line.
    rules = formatter.get_token_style_defs(scope)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return cast("list[str]", rules)


def stylesheet() -> str:
    """Token colours for both modes, scoped to `pre.code`."""
    scope = f"pre.{BLOCK_CLASS}"
    light = "\n".join(_token_rules("light", scope))
    dark = _token_rules("dark", scope)
    dark_block = "\n".join(f"  {line}" for line in dark)
    return (
        f"/* Syntax highlighting (generated by planet.highlight) */\n{light}\n"
        f"@media (prefers-color-scheme: dark) {{\n{dark_block}\n}}\n"
    )
