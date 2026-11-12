from collections.abc import Iterator, Sequence

import pytest

from planet.config import Feed
from planet.model import Entry, FeedMeta, Item
from planet.store import Store

A, B = "https://a.example/feed", "https://b.example/feed"


@pytest.fixture
def store() -> Iterator[Store]:
    s = Store.open(":memory:")
    s.sync_subscriptions([Feed(url=A, name="Alpha"), Feed(url=B, name="beta")])
    yield s
    s.close()


def entry(i: int, date: float | None = None, title: str | None = None) -> Entry:
    return Entry(
        entry_id=f"id-{i}",
        title=title or f"t{i}",
        link=f"https://e/{i}",
        content=f"<p>{i}</p>",
        date=date,
    )


def ids(items: Sequence[Item]) -> list[str]:
    return [i.entry_id for i in items]


def test_sync_adds_renames_and_drops(store: Store) -> None:
    store.upsert_entries(B, [entry(1, date=1.0)], now=10.0)
    store.sync_subscriptions([Feed(url=A, name="Alpha 2")])
    assert [c.name for c in store.channels()] == ["Alpha 2"]
    assert store.select_items(limit=10) == []  # B's entries went with it


def test_validators_round_trip(store: Store) -> None:
    assert store.validators(A) == (None, None)
    store.record_success(A, FeedMeta(title="T"), '"e"', "lm", now=1.0)
    assert store.validators(A) == ('"e"', "lm")
    store.record_not_modified(A, '"e2"', "lm", now=2.0)
    assert store.validators(A) == ('"e2"', "lm")


def test_error_message_shows_until_next_success(store: Store) -> None:
    store.record_error(A, "HTTP 404", now=1.0)
    assert {c.url: c.message for c in store.channels()}[A] == "HTTP 404"
    store.record_success(A, FeedMeta(), None, None, now=2.0)
    assert {c.url: c.message for c in store.channels()}[A] is None


def test_upsert_updates_content_and_keeps_known_date(store: Store) -> None:
    store.upsert_entries(A, [entry(1, date=5.0)], now=100.0)
    store.upsert_entries(A, [entry(1, title="edited")], now=200.0)  # date dropped
    (item,) = store.select_items(limit=10)
    assert item.title == "edited"
    assert item.date == 5.0


def test_undated_entries_get_the_epoch_and_sort_last(store: Store) -> None:
    store.upsert_entries(A, [entry(1)], now=100.0)
    store.upsert_entries(B, [entry(2, date=1.0)], now=100.0)
    assert [(i.entry_id, i.date) for i in store.select_items(limit=10)] == [
        ("id-2", 1.0),
        ("id-1", 0.0),
    ]


def test_prune_keeps_newest_per_feed(store: Store) -> None:
    store.upsert_entries(A, [entry(i, date=float(i)) for i in range(15)], now=0.0)
    store.upsert_entries(B, [entry(100, date=1.0)], now=0.0)
    assert store.prune(keep_per_feed=10) == 5
    items = store.select_items(limit=100)
    assert len(items) == 11
    assert min(i.date for i in items if i.channel.url == A) == 5.0


def test_select_newest_first_with_per_feed_cap_and_limit(store: Store) -> None:
    store.upsert_entries(A, [entry(i, date=float(10 + i)) for i in range(5)], now=0.0)
    store.upsert_entries(B, [entry(100 + i, date=float(i + 1)) for i in range(5)], now=0.0)
    assert ids(store.select_items(limit=3, per_feed=2)) == ["id-4", "id-3", "id-104"]
    assert len(store.select_items(limit=100, per_feed=0)) == 10


def test_same_entry_in_two_feeds_appears_once(store: Store) -> None:
    store.upsert_entries(A, [entry(1, date=2.0)], now=0.0)
    store.upsert_entries(B, [entry(1, date=1.0)], now=0.0)
    (item,) = store.select_items(limit=10)
    assert item.channel.url == A


def test_channels_sorted_by_code_point_like_venus(store: Store) -> None:
    assert [c.name for c in store.channels()] == ["Alpha", "beta"]
