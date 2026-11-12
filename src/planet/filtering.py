"""Per-feed `filter` regexes, with Venus `regexp_sifter` semantics.

The regexes are matched (case-sensitive `re.search`) against the entry's
human-readable text: title, content, summary, author and category terms,
plus the text of alt/title attributes. Markup is stripped, entities decoded,
whitespace collapsed. Every pattern must match for the entry to be kept.
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
    parts = [entry.title, entry.content, entry.summary or "", entry.author_name or "", *entry.tags]
    text = " ".join(_strip_markup(p) for p in parts if p)
    return _SPACE.sub(" ", text).strip()


def keep(feed: Feed, entry: Entry) -> bool:
    if not feed.filters:
        return True
    text = readable_text(entry)
    return all(pattern.search(text) for pattern in feed.filters)
