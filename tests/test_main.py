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
    (static / "sass").mkdir()
    (static / "sass" / "x.sass").write_text("")
    out = tmp_path / "out"
    store = Store.open(tmp_path / "cache.sqlite")
    options = FetchOptions(timeout_s=2, host_interval_s=0)

    first = run(cfg, store, out, static, now=time.time(), deadline=None, options=options)
    assert (first.ok, first.not_modified, first.errors, first.backing_off) == (2, 0, 1, 0)
    assert first.items_rendered == 3  # RSS: 2 Clojure posts (filter), Atom: 1

    html = (out / "index.html").read_text()
    assert "Second Clojure post" in html and "First Clojure post" in html
    assert "Python post" not in html  # filtered out
    assert "<script>" not in html.split('<div id="sidebar">')[0].split("</header>")[1]
    assert 'class="message" title="HTTP 404">Dead Blog</a>' in html
    assert (out / "atom.xml").exists()
    assert (out / "static" / "css" / "screen.css").exists()
    assert not (out / "static" / "sass").exists()

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
