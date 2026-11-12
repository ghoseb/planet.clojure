"""Remove a title that a post repeats at the start of its body.

Many feeds put the post title in the content too, as a heading or a bare
line of text, sometimes inside wrapper elements. The page already shows the
title above the body, so the repeat is dropped.
"""

from __future__ import annotations

import html
import re

from selectolax.lexbor import LexborHTMLParser

from planet.fragments import children

# Elements that may hold just the repeated title. Tables, figures and the like
# are content even when their text happens to match.
_TITLE_HOLDERS = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span", "b", "strong", "-text"}
)
_WRAPPERS = frozenset({"div", "section", "article", "header"})


def _words(text: str) -> str:
    return re.sub(r"\W+", " ", html.unescape(text)).strip().lower()


def drop_repeated_title(fragment: str, title: str) -> str:
    wanted = _words(title)
    if not wanted:
        return fragment
    tree = LexborHTMLParser(fragment)
    node = tree.body
    while node is not None:
        nodes = children(node)
        if not nodes:
            break
        first = nodes[0]
        if first.tag in _TITLE_HOLDERS and _words(first.text(deep=True)) == wanted:
            first.decompose()
            body = tree.body
            return (body.inner_html if body is not None else None) or ""
        node = first if first.tag in _WRAPPERS else None
    return fragment
