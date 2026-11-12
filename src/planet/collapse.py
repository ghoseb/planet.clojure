"""Split long entries into a visible part and a "Read more" part.

The cut is made only between top-level block elements (paragraphs, lists,
code blocks, tables...), never inside one, so both halves are well-formed
HTML. A content that is a single wrapper `<div>` is looked into.
"""

from __future__ import annotations

from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser, LexborNode

from planet.fragments import children as _children

COLLAPSE_OVER_WORDS = 400  # entries longer than this are collapsed
VISIBLE_WORDS = 150  # roughly this much stays visible
MIN_HIDDEN_WORDS = 100  # not worth a "Read more" for less

_BLOCKS = frozenset(
    {
        "address", "blockquote", "details", "dl", "div", "figure", "h1", "h2", "h3", "h4",
        "h5", "h6", "hr", "ol", "p", "pre", "section", "table", "ul", "article", "aside",
    }
)  # fmt: skip
_WRAPPERS = frozenset({"div", "section", "article"})


@dataclass(frozen=True)
class Split:
    visible: str
    more: str | None  # None: show the whole entry


def _words(node: LexborNode) -> int:
    return len((node.text(deep=True, separator=" ") or "").split())


def _top_level(body: LexborNode) -> list[LexborNode]:
    children = _children(body)
    while len(children) == 1 and children[0].tag in _WRAPPERS:
        children = _children(children[0])
    return children


def _html(nodes: list[LexborNode]) -> str:
    return "".join(n.html or "" for n in nodes)


def split(fragment: str) -> Split:
    whole = Split(fragment, None)
    body = LexborHTMLParser(fragment).body
    if body is None or _words(body) <= COLLAPSE_OVER_WORDS:
        return whole
    nodes = _top_level(body)
    seen = 0
    for i, node in enumerate(nodes[:-1]):
        seen += _words(node)
        # Cut only after a block element, so the cut never splits a sentence.
        if node.tag in _BLOCKS and seen >= VISIBLE_WORDS:
            rest = nodes[i + 1 :]
            if sum(_words(n) for n in rest) < MIN_HIDDEN_WORDS:
                return whole
            return Split(_html(nodes[: i + 1]), _html(rest))
    return whole
