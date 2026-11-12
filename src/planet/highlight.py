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
from dataclasses import dataclass
from functools import cache
from typing import cast

from pygments import highlight, lexers
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer
from pygments.token import (
    STANDARD_TYPES,
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    String,
    _TokenType,  # pyright: ignore[reportPrivateUsage]
)
from pygments.util import ClassNotFound
from selectolax.lexbor import LexborHTMLParser, LexborNode

from planet.tailwind import COLOURS

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


# Token colours, all Tailwind colours (planet.tailwind) and all at least WCAG
# AA (4.5:1) against the code background of their mode (tests check this).
# Few hues; structure comes from weight.
CODE_BACKGROUND = {"light": "stone-100", "dark": "stone-900"}


@dataclass(frozen=True)
class Ink:
    """How a token is drawn. `colour` is a Tailwind colour name."""

    colour: str | None = None
    bold: bool = False
    italic: bool = False


_PALETTE: dict[str, dict[_TokenType, Ink]] = {
    "light": {
        Comment: Ink("stone-600", italic=True),
        Keyword: Ink("pink-800", bold=True),
        Name.Builtin: Ink("violet-800"),
        Name.Function: Ink(bold=True),
        String: Ink("green-800"),
        String.Symbol: Ink("blue-800"),  # Clojure keywords, :like-this
        Number: Ink("orange-800"),
        Literal: Ink("orange-800"),
        Keyword.Constant: Ink("orange-800", bold=True),
        Operator.Word: Ink("pink-800", bold=True),
        Generic.Prompt: Ink("stone-600", bold=True),
        Generic.Output: Ink("stone-600"),
        Error: Ink("red-700"),
    },
    "dark": {
        Comment: Ink("stone-400", italic=True),
        Keyword: Ink("pink-300", bold=True),
        Name.Builtin: Ink("violet-300"),
        Name.Function: Ink(bold=True),
        String: Ink("green-300"),
        String.Symbol: Ink("blue-300"),
        Number: Ink("orange-300"),
        Literal: Ink("orange-300"),
        Keyword.Constant: Ink("orange-300", bold=True),
        Operator.Word: Ink("pink-300", bold=True),
        Generic.Prompt: Ink("stone-400", bold=True),
        Generic.Output: Ink("stone-400"),
        Error: Ink("red-300"),
    },
}


def palette(mode: str) -> dict[_TokenType, Ink]:
    return _PALETTE[mode]


def _ink(token: _TokenType, inks: dict[_TokenType, Ink]) -> Ink:
    """A token's ink, inherited from its ancestors as in Pygments styles."""
    lineage: list[_TokenType] = []
    node: _TokenType | None = token
    while node is not None:
        lineage.append(node)
        node = node.parent
    ink = Ink()
    for ancestor in reversed(lineage):
        own = inks.get(ancestor)
        if own is not None:
            ink = Ink(own.colour or ink.colour, own.bold or ink.bold, own.italic or ink.italic)
    return ink


def _token_rules(mode: str, scope: str) -> list[str]:
    """One rule per Pygments token class, as Pygments' own formatter would
    write them, but with oklch colours (Pygments styles accept only hex)."""
    rules: list[str] = []
    for token, css_class in STANDARD_TYPES.items():
        ink = _ink(token, _PALETTE[mode])
        declarations = [
            *([f"color: {COLOURS[ink.colour]}"] if ink.colour else []),
            *(["font-weight: bold"] if ink.bold else []),
            *(["font-style: italic"] if ink.italic else []),
        ]
        if css_class and declarations:
            name = str(token).removeprefix("Token.")
            label = f"{name}, {ink.colour}" if ink.colour else name
            rules.append(f"{scope} .{css_class} {{ {'; '.join(declarations)} }} /* {label} */")
    return rules


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
