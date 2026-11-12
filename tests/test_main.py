import time
from pathlib import Path

from conftest import FeedServer
from planet.config import Config, parse
from planet.fetch import Download, FetchOptions
from planet.main import prepare, run
from planet.store import Store


def config(server: FeedServer) -> Config:
    return parse(f"""
[Planet]
name = Test Planet
link = https://planet.example/
items_per_page = 15
new_feed_items = 2

[{server.url("/rss.xml")}]
name = RSS Blog
filter = (clojure|Clojure|\\(def |\\(defn-? )

[{server.url("/atom.xml")}]
name = Atom Blog

[{server.url("/missing")}]
name = Dead Blog
""")


def test_end_to_end_twice(server: FeedServer, tmp_path: Path) -> None:
    cfg = config(server)
    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    (static / "css" / "screen.css").write_text("body{}")
    (static / "css" / "style.css").write_text("main{}")
    out = tmp_path / "out"
    store = Store.open(tmp_path / "cache.sqlite")
    options = FetchOptions(timeout_s=2, host_interval_s=0)

    first = run(cfg, store, out, static, now=time.time(), deadline=None, options=options)
    assert (first.ok, first.not_modified, first.errors, first.backing_off) == (2, 0, 1, 0)
    assert first.items_rendered == 3  # RSS: 2 Clojure posts (filter), Atom: 1

    html = (out / "index.html").read_text()
    assert "Second Clojure post" in html and "First Clojure post" in html
    assert "Python post" not in html  # filtered out
    assert "<script" not in html
    assert 'class="message" title="HTTP 404">Dead Blog</a>' in html
    assert (out / "atom.xml").exists()
    assert (out / "static" / "css" / "screen.css").exists()
    # style.css is published only under its content hash, which the page links
    (css,) = (out / "static" / "css").glob("style.*.css")
    assert css.read_text().startswith("main{}")
    assert f'href="/static/css/{css.name}"' in html
    assert not (out / "static" / "css" / "style.css").exists()

    # second run: RSS answers 304 to the stored ETag, history is kept, and
    # the dead feed is backing off: not requested, still marked failing
    rss_hits, missing_hits = server.hits["/rss.xml"], server.hits["/missing"]
    second = run(cfg, store, out, static, now=time.time(), deadline=None, options=options)
    assert (second.not_modified, second.errors, second.backing_off) == (1, 0, 1)
    assert server.hits["/rss.xml"] == rss_hits + 1
    assert server.hits["/missing"] == missing_hits
    assert second.items_rendered == 3
    assert 'class="message" title="HTTP 404">Dead Blog</a>' in (out / "index.html").read_text()
    store.close()


def test_rate_limited_feed_is_deferred_not_failed(server: FeedServer, tmp_path: Path) -> None:
    url = server.url("/always-429?t=main", host="localhost")
    cfg = parse(f"[Planet]\nname = P\nlink = https://planet.example/\n\n[{url}]\nname = Busy\n")
    store = Store.open(tmp_path / "cache.sqlite")
    options = FetchOptions(timeout_s=2, host_interval_s=0, rate_limit_pause_s=0.05)
    stats = run(cfg, store, tmp_path / "out", None, now=time.time(), deadline=None, options=options)
    assert (stats.errors, stats.deferred) == (0, 1)
    assert store.backing_off(time.time()) == set()  # tried again next run
    assert [c.message for c in store.channels()] == [None]
    store.close()


def test_host_budget_rotates_through_feeds(server: FeedServer, tmp_path: Path) -> None:
    paths = [f"/atom.xml?t=budget&i={i}" for i in range(3)]
    sections = "".join(
        f"[{server.url(p, 'localhost')}]\nname = B{i}\n\n" for i, p in enumerate(paths)
    )
    cfg = parse(f"[Planet]\nname = P\nlink = https://planet.example/\n\n{sections}")
    store = Store.open(tmp_path / "cache.sqlite")
    options = FetchOptions(timeout_s=2, host_interval_s=0)

    def go(now: float) -> int:
        return run(
            cfg,
            store,
            tmp_path / "out",
            None,
            now=now,
            deadline=None,
            options=options,
            per_host_budget=2,
        ).deferred

    assert go(now=1000.0) == 1
    assert [server.hits.get(p, 0) for p in paths] == [1, 1, 0]
    assert go(now=2000.0) == 1  # the feed left over goes first, then the oldest
    assert [server.hits.get(p, 0) for p in paths] == [2, 1, 1]
    store.close()


def test_filter_runs_on_sanitized_entries() -> None:
    feed = parse(
        "[Planet]\nname = P\nlink = https://planet.example/\n\n"
        "[https://f.example/rss]\nname = F\nfilter = Clojure\n"
    ).feeds[0]
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>F</title>
      <item><guid isPermaLink="false">a</guid><title>Kept</title>
        <description>&lt;p&gt;Clojure tips&lt;/p&gt;</description></item>
      <item><guid isPermaLink="false">b</guid><title>Dropped</title>
        <description>&lt;p&gt;hi&lt;/p&gt;&lt;script&gt;Clojure()&lt;/script&gt;</description></item>
    </channel></rss>"""
    parsed = prepare(feed, Download(feed.url, rss, "application/rss+xml"))
    # "Clojure" only inside <script>, which the sanitizer removes
    assert [e.title for e in parsed.entries] == ["Kept"]


def translated_feed(*langs: str) -> bytes:
    links = "".join(
        f'&lt;link rel="alternate" hreflang="{lang}" href="post_{lang}.html"&gt;' for lang in langs
    )
    entries = "".join(
        f"""<entry><id>urn:{lang}</id><title>Clojure post ({lang})</title>
        <updated>2026-01-01T00:00:00Z</updated>
        <link href="https://b.example/post_{lang}.html"/>
        <content type="html">&lt;html lang="{lang}"&gt;&lt;head&gt;{links}&lt;/head&gt;
        &lt;body&gt;&lt;p&gt;Clojure&lt;/p&gt;&lt;/body&gt;&lt;/html&gt;</content></entry>"""
        for lang in langs
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>B</title><id>urn:b</id>
    <updated>2026-01-01T00:00:00Z</updated>{entries}</feed>""".encode()


def test_only_one_language_version_of_a_post_is_kept() -> None:
    feed = parse(
        "[Planet]\nname = P\nlink = https://planet.example/\n\n[https://b.example/feed]\nname = B\n"
    ).feeds[0]
    parsed = prepare(feed, Download(feed.url, translated_feed("de", "en"), None))
    assert [e.title for e in parsed.entries] == ["Clojure post (en)"]
    assert parsed.dropped_translations == {"urn:de"}


def test_dropped_translations_are_deleted_from_the_cache(tmp_path: Path) -> None:
    feed_url = "https://b.example/feed"
    store = Store.open(tmp_path / "cache.sqlite")
    cfg = parse(f"[Planet]\nname = P\nlink = https://planet.example/\n\n[{feed_url}]\nname = B\n")
    store.sync_subscriptions(cfg.feeds)
    old = prepare(cfg.feeds[0], Download(feed_url, translated_feed("de"), None))
    store.upsert_entries(feed_url, old.entries, now=0.0)  # a run before the English one
    new = prepare(cfg.feeds[0], Download(feed_url, translated_feed("de", "en"), None))
    store.upsert_entries(feed_url, new.entries, now=1.0)
    store.delete_entries(feed_url, new.dropped_translations)
    assert [i.entry_id for i in store.select_items(limit=10)] == ["urn:en"]
    store.close()
