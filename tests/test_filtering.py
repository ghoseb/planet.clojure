import re
from dataclasses import replace
from typing import Any

from planet.config import Feed
from planet.filtering import keep, readable_text
from planet.model import Entry

CLOJURE = Feed(url="u", name="n", filters=(re.compile(r"(clojure|Clojure|\(def |\(defn-? )"),))
BASE = Entry(entry_id="id", title="", link="https://x.example/clojure", content="")


def entry(**changes: Any) -> Entry:
    return replace(BASE, **changes)


def test_no_filter_keeps_everything() -> None:
    assert keep(Feed(url="u", name="n"), entry(title="anything"))


def test_matches_title_content_summary_author_tags() -> None:
    assert keep(CLOJURE, entry(title="Why Clojure"))
    assert keep(CLOJURE, entry(content="<p>(defn foo [])</p>"))
    assert keep(CLOJURE, entry(summary="clojure tips"))
    assert keep(CLOJURE, entry(tags=("clojure",)))


def test_case_sensitive_like_venus() -> None:
    assert not keep(CLOJURE, entry(title="CLOJURE"))


def test_ignores_markup_and_links_but_reads_alt_text() -> None:
    assert not keep(CLOJURE, entry(content='<a href="https://clojure.org">site</a>'))
    assert keep(CLOJURE, entry(content='<img src="x.png" alt="Clojure logo">'))


def test_entities_decoded_and_whitespace_collapsed() -> None:
    text = readable_text(entry(title="a &\n\n b", content="<p>c &amp; d</p>"))
    assert text == "a & b c & d"


def test_title_is_plain_text_after_sanitizing() -> None:
    # a sanitized title keeps literal "<...>" and "&lt;": not markup, not entities
    assert (
        readable_text(entry(title="Using <div> in Hiccup &lt;3")) == "Using <div> in Hiccup &lt;3"
    )


def test_all_patterns_must_match() -> None:
    feed = Feed(url="u", name="n", filters=(re.compile("Clojure"), re.compile("Datomic")))
    assert keep(feed, entry(title="Clojure and Datomic"))
    assert not keep(feed, entry(title="Clojure only"))
