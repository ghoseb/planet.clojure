from dataclasses import replace

from planet.model import Entry
from planet.translations import one_per_post

BASE = "https://blog.example/"


def post(slug: str, lang: str | None, date: float | None = 1.0, *others: str) -> Entry:
    """Entry for BASE/<slug>_<lang>.html declaring the given other versions."""
    link = f"{BASE}{slug}_{lang}.html" if lang else f"{BASE}{slug}.html"
    return Entry(
        entry_id=link,
        title=slug,
        link=link,
        content="",
        date=date,
        content_language=lang,
        translations=tuple((f"{BASE}{slug}_{o}.html", o) for o in (lang, *others) if o),
    )


def ids(entries: tuple[Entry, ...]) -> list[str]:
    return [e.entry_id for e in entries]


def test_english_version_is_kept() -> None:
    en, de = post("fork", "en", 1.0, "de"), post("fork", "de", 1.0, "en")
    result = one_per_post([de, en])
    assert ids(result.kept) == [en.entry_id]
    assert result.dropped == {de.entry_id}


def test_regional_english_counts_as_english() -> None:
    us, fr = post("p", "en-US", 2.0, "fr"), post("p", "fr", 1.0, "en-US")
    assert ids(one_per_post([fr, us]).kept) == [us.entry_id]


def test_without_english_the_earliest_version_is_kept() -> None:
    de, fr = post("p", "de", 2.0, "fr"), post("p", "fr", 1.0, "de")
    assert ids(one_per_post([de, fr]).kept) == [fr.entry_id]


def test_language_may_come_from_the_other_versions_links() -> None:
    en = post("p", "en", 1.0, "de")
    de = replace(post("p", "de", 1.0, "en"), content_language=None)
    en = replace(en, content_language=None)
    assert ids(one_per_post([de, en]).kept) == [en.entry_id]


def test_one_sided_links_still_group() -> None:
    en = replace(post("p", "en"), translations=())
    de = post("p", "de", 1.0, "en")
    assert ids(one_per_post([de, en]).kept) == [en.entry_id]


def test_different_posts_and_plain_entries_are_untouched() -> None:
    entries = [
        post("a", "en", 1.0, "de"),
        post("b", "de", 1.0, "en"),  # its English version is not in the feed
        post("c", None),
        Entry(entry_id="x", title="x", link=None, content=""),
    ]
    result = one_per_post(entries)
    assert result.kept == tuple(entries)
    assert result.dropped == frozenset()
