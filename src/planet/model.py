"""Plain data passed between parse, filter, store and render."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedMeta:
    """Channel-level information taken from a source feed."""

    title: str | None = None
    link: str | None = None  # the blog's website (html alternate link)
    subtitle: str | None = None
    feed_id: str | None = None
    updated: float | None = None  # epoch seconds, UTC
    rights: str | None = None
    language: str | None = None
    author_name: str | None = None
    author_email: str | None = None


@dataclass(frozen=True)
class Entry:
    """One feed entry, as parsed (content may be unsanitized HTML)."""

    entry_id: str
    title: str  # may contain HTML when parsed
    link: str | None
    content: str  # HTML: content if present, else summary
    summary: str | None = None  # HTML; read by filters, never rendered or stored
    author_name: str | None = None
    author_email: str | None = None
    tags: tuple[str, ...] = ()  # category terms, for filter matching
    # Venus semantics: `updated` if present, else `published`. None when the
    # feed gives neither; the store then keeps a known date, else the epoch.
    date: float | None = None
    title_language: str | None = None
    content_language: str | None = None


@dataclass(frozen=True)
class ParsedFeed:
    meta: FeedMeta
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Channel:
    """A subscription as shown in the sidebar / atom <source>."""

    url: str  # the feed URL from config.ini
    name: str  # the name from config.ini
    meta: FeedMeta
    message: str | None = None  # last fetch error, if the last fetch failed


@dataclass(frozen=True)
class Item:
    """An entry selected for rendering, with its channel."""

    entry_id: str
    title: str  # plain text
    link: str | None
    content: str  # sanitized HTML
    author_name: str | None
    author_email: str | None
    date: float  # epoch seconds, UTC
    title_language: str | None
    content_language: str | None
    channel: Channel
