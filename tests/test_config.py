from planet.config import parse

CONFIG = """
[Planet]
name = Test Planet
link = https://planet.example/
new_feed_items = 2
items_per_page = 15
date_format = %B %d, %Y %I:%M %p
owner_name = ignored

[https://a.example/feed]
name = "O'Reilly Radar"
twitter = ignored

[https://b.example/feed]
name = First
filter = (clojure|Clojure)

[https://b.example/feed]
name = Second

[typo://c.example/feed]
name = Typo
"""


def test_settings() -> None:
    s = parse(CONFIG).settings
    assert s.name == "Test Planet"
    assert s.new_feed_items == 2
    assert s.items_per_page == 15
    assert s.date_format == "%B %d, %Y %I:%M %p"  # `%` left alone
    assert s.feed == "https://planet.example/atom.xml"  # defaults to atom.xml under link


def test_feeds() -> None:
    feeds = {f.url: f for f in parse(CONFIG).feeds}
    # every section but [Planet] is a feed, even malformed ones
    assert set(feeds) == {
        "https://a.example/feed",
        "https://b.example/feed",
        "typo://c.example/feed",
    }
    assert feeds["https://a.example/feed"].name == "O'Reilly Radar"  # quotes stripped
    assert feeds["https://a.example/feed"].filters == ()
    # duplicate sections merge, later keys win, earlier keys survive
    b = feeds["https://b.example/feed"]
    assert b.name == "Second"
    assert [p.pattern for p in b.filters] == ["(clojure|Clojure)"]


def test_explicit_feed_url_wins() -> None:
    cfg = parse(
        CONFIG.replace("new_feed_items = 2", "new_feed_items = 2\nfeed = https://x.example/f.xml")
    )
    assert cfg.settings.feed == "https://x.example/f.xml"
