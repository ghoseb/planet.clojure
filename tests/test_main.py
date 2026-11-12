import time
from pathlib import Path

from conftest import FeedServer
from planet.config import Config, parse
from planet.fetch import FetchOptions
from planet.main import run
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
    options = FetchOptions(timeout_s=2)

    first = run(cfg, store, out, static, now=time.time(), deadline=None, options=options)
    assert (first.ok, first.not_modified, first.errors) == (2, 0, 1)
    assert first.items_rendered == 3  # RSS: 2 Clojure posts (filter), Atom: 1

    html = (out / "index.html").read_text()
    assert "Second Clojure post" in html and "First Clojure post" in html
    assert "Python post" not in html  # filtered out
    assert "<script>" not in html.split('<div id="sidebar">')[0].split("</header>")[1]
    assert 'class="message" title="HTTP 404">Dead Blog</a>' in html
    assert (out / "atom.xml").exists()
    assert (out / "static" / "css" / "screen.css").exists()
    assert not (out / "static" / "sass").exists()

    # second run: RSS answers 304 to the stored ETag, history is kept
    rss_hits = server.hits["/rss.xml"]
    second = run(cfg, store, out, static, now=time.time(), deadline=None, options=options)
    assert second.not_modified == 1
    assert server.hits["/rss.xml"] == rss_hits + 1
    assert second.items_rendered == 3
    store.close()
