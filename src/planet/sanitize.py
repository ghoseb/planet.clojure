"""Make third-party feed HTML safe to embed in our page.

Feed content from ~850 blogs ends up inline in index.html, so it must not be
able to run script, add event handlers, or use javascript: URLs. nh3 (Rust
`ammonia`) does allowlist-based cleaning; its defaults allow ordinary
formatting, links, images, code blocks and tables.
"""

from __future__ import annotations

import html
from dataclasses import replace

import nh3

from planet.model import Entry


def clean_html(fragment: str) -> str:
    return nh3.clean(fragment, link_rel="noopener noreferrer nofollow")


def plain_text(fragment: str) -> str:
    """Markup removed, entities decoded. Escape again when rendering."""
    return html.unescape(nh3.clean(fragment, tags=set())).strip()


def sanitize_entry(entry: Entry) -> Entry:
    return replace(
        entry,
        title=plain_text(entry.title),
        content=clean_html(entry.content),
        summary=None,  # only needed for filtering, which happens before this
    )
