"""Turn raw feed bytes into ParsedFeed (feedparser does the heavy lifting).

feedparser is untyped and returns loosely shaped dicts. Everything read from
it goes through the small accessors below, which return a value only when
it has the expected type, so odd feeds degrade to None instead of crashing.
"""

from __future__ import annotations

import calendar
import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import feedparser  # pyright: ignore[reportMissingTypeStubs]

from planet.model import Entry, FeedMeta, ParsedFeed

type Raw = Mapping[str, Any]

# feedparser's dict remaps a missing updated_parsed to published_parsed (with a
# deprecation warning); the plain dict lookup doesn't.
_plain_get = cast("Callable[[Raw, str], object]", dict.get)


class ParseError(Exception):
    pass


def _str(obj: Raw, key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) else None


def _map(obj: Raw, key: str) -> Raw:
    value = obj.get(key)
    return cast("Raw", value) if isinstance(value, Mapping) else {}


def _maps(obj: Raw, key: str) -> list[Raw]:
    value = obj.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    items = cast("Sequence[object]", value)
    return [cast("Raw", v) for v in items if isinstance(v, Mapping)]


def _epoch(obj: Raw, key: str) -> float | None:
    value = _plain_get(obj, key) if isinstance(obj, dict) else obj.get(key)
    if not isinstance(value, time.struct_time):
        return None
    try:
        return float(calendar.timegm(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _detail(obj: Raw, key: str) -> tuple[str | None, str | None]:
    """(value, language) of a feedparser *_detail field."""
    detail = _map(obj, f"{key}_detail")
    if detail:
        return _str(detail, "value"), _str(detail, "language")
    return _str(obj, key), None


def _html_link(feed: Raw) -> str | None:
    for link in _maps(feed, "links"):
        if _str(link, "rel") == "alternate" and "html" in (_str(link, "type") or ""):
            return _str(link, "href")
    return _str(feed, "link")


def _entry_link(entry: Raw) -> str | None:
    for link in _maps(entry, "links"):
        if _str(link, "rel") == "alternate":
            return _str(link, "href")
    return _str(entry, "link")


def _entry_id(entry: Raw, link: str | None, title: str, content: str) -> str:
    if entry_id := _str(entry, "id"):
        return entry_id
    if link:
        return link
    # Not security-sensitive: just a stable id for entries that lack one.
    digest = hashlib.sha1(f"{title}\n{content}".encode(), usedforsecurity=False).hexdigest()
    return f"urn:sha1:{digest}"


def _to_entry(entry: Raw) -> Entry:
    title, title_language = _detail(entry, "title")
    summary, _ = _detail(entry, "summary")
    contents = _maps(entry, "content")
    if contents:
        content = _str(contents[0], "value") or ""
        content_language = _str(contents[0], "language")
    else:
        content = summary or ""
        content_language = _str(_map(entry, "summary_detail"), "language")
    link = _entry_link(entry)
    author = _map(entry, "author_detail")
    return Entry(
        entry_id=_entry_id(entry, link, title or "", content),
        title=title or "",
        link=link,
        content=content,
        summary=summary,
        author_name=_str(author, "name") or _str(entry, "author"),
        author_email=_str(author, "email"),
        tags=tuple(term for t in _maps(entry, "tags") if (term := _str(t, "term"))),
        date=_epoch(entry, "updated_parsed") or _epoch(entry, "published_parsed"),
        title_language=title_language,
        content_language=content_language,
    )


def parse_feed(body: bytes, url: str, content_type: str | None = None) -> ParsedFeed:
    """Parse feed bytes. `content_type` is the HTTP header (feedparser uses
    its charset). Raises ParseError if nothing usable came out.

    A well-formed feed with no entries is fine: some servers answer
    If-Modified-Since with only the entries newer than that date, which may
    be none.
    """
    headers = {"content-location": url}
    if content_type:
        headers["content-type"] = content_type
    data = cast(
        "Raw",
        feedparser.parse(  # pyright: ignore[reportUnknownMemberType]
            body, response_headers=headers
        ),
    )
    feed = _map(data, "feed")
    entries = _maps(data, "entries")
    if not entries and (data.get("bozo") or not data.get("version")):
        # malformed, or not a feed at all (e.g. an HTML page)
        reason = data.get("bozo_exception") or "not a recognized feed format"
        raise ParseError(f"unparseable feed: {reason!r}"[:200])

    author = _map(feed, "author_detail")
    meta = FeedMeta(
        title=_detail(feed, "title")[0],
        link=_html_link(feed),
        subtitle=_detail(feed, "subtitle")[0],
        feed_id=_str(feed, "id"),
        updated=_epoch(feed, "updated_parsed"),
        rights=_detail(feed, "rights")[0],
        language=_str(feed, "language") or _str(_map(feed, "title_detail"), "language"),
        author_name=_str(author, "name") or _str(feed, "author"),
        author_email=_str(author, "email"),
    )

    # Venus: when a feed repeats an id, keep the newest version.
    by_id: dict[str, Entry] = {}
    for raw in entries:
        entry = _to_entry(raw)
        seen = by_id.get(entry.entry_id)
        if seen is None or (entry.date or 0) >= (seen.date or 0):
            by_id[entry.entry_id] = entry
    return ParsedFeed(meta=meta, entries=tuple(by_id.values()))
