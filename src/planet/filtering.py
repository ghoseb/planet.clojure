"""Per-feed `filter` regexes, with Venus `regexp_sifter` semantics.

The regexes are matched (case-sensitive `re.search`) against the entry's
human-readable text: title, content, summary, author and category terms,
plus the text of alt/title attributes. Entries are filtered after
sanitizing, as Venus did, so text the sanitizer removes (scripts, styles)
can't match. Markup is stripped from the HTML fields (content, summary) and
entities decoded; the title is already plain text by then. Whitespace is
collapsed. Every pattern must match for the entry to be kept.
"""

from __future__ import annotations

import html
import re

from planet.config import Feed
from planet.model import Entry

_ATTR_TEXT = re.compile(r"""<[^>]*\s(?:alt|title)=['"]([^'"]*)['"][^>]*>""")
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _strip_markup(fragment: str) -> str:
    fragment = _ATTR_TEXT.sub(r" \1 ", fragment)
    fragment = _TAGS.sub(" ", fragment)
    return html.unescape(fragment)


def readable_text(entry: Entry) -> str:
    """Expects a sanitized entry: plain-text title, HTML content/summary."""
    parts = [
        entry.title,
        _strip_markup(entry.content),
        _strip_markup(entry.summary or ""),
        entry.author_name or "",
        *entry.tags,
    ]
    text = " ".join(p for p in parts if p)
    return _SPACE.sub(" ", text).strip()


def keep(feed: Feed, entry: Entry) -> bool:
    if not feed.filters:
        return True
    text = readable_text(entry)
    return all(pattern.search(text) for pattern in feed.filters)
