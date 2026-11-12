"""Make third-party feed HTML safe to embed in our page.

Feed content from ~850 blogs ends up inline in index.html, so it must not be
able to run script, add event handlers, or use javascript: URLs. nh3 (Rust
`ammonia`) does allowlist-based cleaning; its defaults allow ordinary
formatting, links, images, code blocks and tables.
"""

from __future__ import annotations

import html
import re
from dataclasses import replace

import nh3

from planet.highlight import language_label
from planet.model import Entry

# nh3's defaults, plus `class` on code blocks: only to carry the language
# label, which `_code_language` reduces to `language-<alias>`.
_CODE_TAGS = ("pre", "code")
_ATTRIBUTES = {tag: set(attrs) for tag, attrs in nh3.ALLOWED_ATTRIBUTES.items()} | {
    tag: {*nh3.ALLOWED_ATTRIBUTES.get(tag, ()), "class"} for tag in _CODE_TAGS
}


def _code_language(tag: str, attribute: str, value: str) -> str | None:
    """nh3 attribute filter: a code block's class becomes its language label."""
    if attribute != "class" or tag not in _CODE_TAGS:
        return value
    language = language_label(value)
    return f"language-{language}" if language else None


# These elements hold fallback markup (Medium puts a link to each embed inside
# an <iframe>), but an HTML parser reads their content as raw text, so nh3
# would escape it. Dropping just the tags keeps the fallback as markup.
_FALLBACK_WRAPPERS = re.compile(r"</?(?:iframe|noscript|noembed|noframes)\b[^>]*>", re.IGNORECASE)


def clean_html(fragment: str) -> str:
    return nh3.clean(
        _FALLBACK_WRAPPERS.sub("", fragment),
        attributes=_ATTRIBUTES,
        attribute_filter=_code_language,
        link_rel="noopener noreferrer nofollow",
    )


def plain_text(fragment: str) -> str:
    """Markup removed, entities decoded. Escape again when rendering."""
    return html.unescape(nh3.clean(fragment, tags=set())).strip()


def sanitize_entry(entry: Entry) -> Entry:
    return replace(
        entry,
        title=plain_text(entry.title),
        content=clean_html(entry.content),
        # Not rendered or stored, but filters read it (after sanitizing, as
        # in Venus).
        summary=clean_html(entry.summary) if entry.summary else None,
    )
