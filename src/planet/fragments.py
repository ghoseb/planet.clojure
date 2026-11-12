"""Helpers for walking parsed HTML fragments."""

from __future__ import annotations

from selectolax.lexbor import LexborNode


def children(node: LexborNode) -> list[LexborNode]:
    """Element and non-blank text children, in order."""
    return [
        child
        for child in node.iter(include_text=True)
        if child.tag != "-text" or (child.text_content or "").strip()
    ]
