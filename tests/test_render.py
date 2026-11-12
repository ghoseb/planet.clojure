import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from planet.config import parse
from planet.model import Channel, FeedMeta, Item
from planet.render import render

SETTINGS = parse("""
[Planet]
name = Test Planet
link = https://planet.example/
date_format = %B %d, %Y %I:%M %p
""").settings

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
ITEM = Item(
    entry_id="urn:1",
    title="A <b> & c",
    link="https://blog.example/1",
    content="<p>Hello <em>world</em></p>",
    author_name=None,
    author_email=None,
    date=1_762_000_000.0,
    title_language=None,
    content_language=None,
    channel=Channel(
        url="https://blog.example/feed",
        name="Blog <Name>",
        meta=FeedMeta(title="Blog & co", link="https://blog.example/"),
    ),
)


def item(**changes: Any) -> Item:
    return replace(ITEM, **changes)


def find(el: ET.Element, path: str) -> ET.Element:
    found = el.find(path, ATOM_NS)
    assert found is not None, path
    return found


def text(el: ET.Element, path: str) -> str | None:
    return find(el, path).text


def pages(
    items: Sequence[Item] | None = None, channels: Sequence[Channel] | None = None
) -> dict[str, str]:
    items = [item()] if items is None else items
    channels = [items[0].channel] if channels is None and items else (channels or [])
    return render(SETTINGS, items, channels, now=1_762_100_000.0)


def test_index_escapes_text_and_keeps_sanitized_content() -> None:
    html = pages()["index.html"]
    assert "A &lt;b&gt; &amp; c" in html  # title is text
    assert "Blog &lt;Name&gt;" in html  # channel name is text
    assert "<p>Hello <em>world</em></p>" in html  # content is (sanitized) HTML
    assert "November 01, 2025" in html  # date_format applied, UTC


def test_index_links_to_the_configured_feed() -> None:
    html = pages()["index.html"]
    assert html.count('href="https://planet.example/atom.xml"') == 2  # <head> and sidebar
    assert "planet.clojure.in" not in html


def test_sidebar_marks_failed_feeds() -> None:
    failed = Channel(
        url="https://dead.example/feed", name="Dead", meta=FeedMeta(), message="HTTP 404"
    )
    html = pages(channels=[failed])["index.html"]
    assert 'class="message" title="HTTP 404">Dead</a>' in html


def test_atom_is_valid_and_content_escaped_once() -> None:
    root = ET.fromstring(pages()["atom.xml"].encode())
    assert text(root, "a:id") == "https://planet.example/atom.xml"
    entry = find(root, "a:entry")
    assert text(entry, "a:title") == "A <b> & c"
    assert text(entry, "a:content") == "<p>Hello <em>world</em></p>"
    assert text(entry, "a:updated") == "2025-11-01T12:26:40+00:00"
    # author falls back to the channel name
    assert text(entry, "a:author/a:name") == "Blog <Name>"
    assert find(entry, "a:source/a:link").get("href") == "https://blog.example/feed"


def test_empty_planet_renders() -> None:
    out = pages(items=[], channels=[])
    assert "<title>Test Planet</title>" in out["index.html"]
    ET.fromstring(out["atom.xml"].encode())
