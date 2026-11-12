import calendar

import pytest

from conftest import ATOM, RSS
from planet.parse import ParseError, parse_feed


def ts(s: str) -> float:
    import time

    return float(calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ")))


def test_rss() -> None:
    feed = parse_feed(RSS, "https://rss.example/feed")
    assert feed.meta.title == "RSS Blog"
    assert feed.meta.link == "https://rss.example/"
    assert [e.entry_id for e in feed.entries] == ["rss-1", "rss-2", "rss-3"]
    first = feed.entries[0]
    assert first.link == "https://rss.example/1"
    assert first.date == ts("2026-11-02T10:00:00Z")
    assert "(defn foo [])" in first.content


def test_atom_prefers_updated_over_published() -> None:
    feed = parse_feed(ATOM, "https://atom.example/feed")
    assert feed.meta.feed_id == "urn:atom-blog"
    assert feed.meta.link == "https://atom.example/"
    (entry,) = feed.entries
    assert entry.date == ts("2026-11-05T12:00:00Z")
    # feed-level author stays on the feed; the template falls back to it
    assert feed.meta.author_name == "Ada"


def test_missing_ids_fall_back_to_link_then_hash() -> None:
    body = b"""<rss version="2.0"><channel><title>t</title>
      <item><title>a</title><link>https://e.x/a</link></item>
      <item><title>b</title><description>no link</description></item>
    </channel></rss>"""
    a, b = parse_feed(body, "u").entries
    assert a.entry_id == "https://e.x/a"
    assert b.entry_id.startswith("urn:sha1:")
    assert a.date is None


def test_repeated_id_keeps_newest() -> None:
    body = b"""<rss version="2.0"><channel><title>t</title>
      <item><guid>x</guid><title>old</title><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item>
      <item><guid>x</guid><title>new</title><pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    (entry,) = parse_feed(body, "u").entries
    assert entry.title == "new"


def test_empty_but_valid_feed_is_not_an_error() -> None:
    # e.g. a server answering If-Modified-Since with only newer entries (none)
    body = b"""<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
      <title></title><id>https://e.x/feed.xml</id><updated>2026-11-12T05:55:51Z</updated>
    </feed>"""
    feed = parse_feed(body, "https://e.x/feed.xml", "application/atom+xml")
    assert feed.entries == ()
    assert feed.meta.feed_id == "https://e.x/feed.xml"


def test_html_page_raises() -> None:
    body = b"<!doctype html><html><head><title>Site</title></head><body>hi</body></html>"
    with pytest.raises(ParseError):
        parse_feed(body, "https://e.x/feed/", "text/html; charset=UTF-8")


def test_charset_from_content_type_is_used() -> None:
    body = """<?xml version="1.0"?><rss version="2.0"><channel><title>Caf\xe9</title>
      <item><title>\xe9t\xe9</title><guid>1</guid></item></channel></rss>""".encode("latin-1")
    feed = parse_feed(body, "u", "application/rss+xml; charset=iso-8859-1")
    assert feed.meta.title == "Caf\xe9"
    assert feed.entries[0].title == "\xe9t\xe9"


def test_garbage_raises() -> None:
    with pytest.raises(ParseError):
        parse_feed(b"\x00\x01 definitely not a feed", "u")


TRANSLATED_ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title><id>urn:t</id>
<updated>2026-01-01T00:00:00Z</updated>
<entry><id>urn:en</id><title>Fork</title><updated>2026-01-01T00:00:00Z</updated>
  <link href="https://b.example/fork_en.html"/>
  <content type="html">&lt;html lang="en"&gt;&lt;head&gt;
    &lt;link rel="alternate" hreflang="en" href="fork_en.html"&gt;
    &lt;link rel="alternate" hreflang="de" href="fork_de.html"&gt;
  &lt;/head&gt;&lt;body&gt;&lt;p&gt;Hello&lt;/p&gt;&lt;/body&gt;&lt;/html&gt;</content></entry>
<entry><id>urn:atom</id><title>Atom links</title><updated>2026-01-01T00:00:00Z</updated>
  <link rel="alternate" href="https://b.example/p"/>
  <link rel="alternate" hreflang="fr" href="https://b.example/fr/p"/>
  <content type="html">&lt;p&gt;Hi&lt;/p&gt;</content></entry>
</feed>"""


def test_language_hints_from_embedded_page_and_atom_links() -> None:
    page, atom = parse_feed(TRANSLATED_ATOM, "https://b.example/feed").entries
    assert page.content_language == "en"
    assert page.translations == (
        ("https://b.example/fork_en.html", "en"),
        ("https://b.example/fork_de.html", "de"),
    )
    assert atom.translations == (("https://b.example/fr/p", "fr"),)
    assert atom.content_language is None
