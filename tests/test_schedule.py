from planet.config import Feed
from planet.schedule import plan

M = [Feed(url=f"https://medium.com/feed/@{i}", name=f"m{i}") for i in range(5)]
OTHER = Feed(url="https://blog.example/feed", name="other")


def urls(feeds: tuple[Feed, ...]) -> list[str]:
    return [f.url for f in feeds]


def test_each_host_gets_at_most_its_budget_in_config_order_at_first() -> None:
    p = plan([*M, OTHER], last_fetched={}, backing_off=set(), per_host_budget=2)
    assert urls(p.fetch) == [M[0].url, M[1].url, OTHER.url]
    assert urls(p.over_budget) == urls(tuple(M[2:]))


def test_least_recently_fetched_go_first_never_fetched_before_all() -> None:
    last = {M[0].url: 300.0, M[1].url: 100.0, M[2].url: 200.0, M[3].url: None}
    p = plan(M[:4], last_fetched=last, backing_off=set(), per_host_budget=2)
    assert urls(p.fetch) == [M[3].url, M[1].url]  # never fetched, then oldest
    assert urls(p.over_budget) == [M[2].url, M[0].url]


def test_backing_off_feeds_are_left_out_and_dont_use_the_budget() -> None:
    p = plan(M[:3], last_fetched={}, backing_off={M[0].url}, per_host_budget=2)
    assert urls(p.fetch) == [M[1].url, M[2].url]
    assert urls(p.backing_off) == [M[0].url]
    assert p.over_budget == ()


def test_rotation_reaches_every_feed() -> None:
    last: dict[str, float | None] = {}
    seen: list[str] = []
    for run in range(3):  # 5 feeds, budget 2: everyone within 3 runs
        p = plan(M, last_fetched=last, backing_off=set(), per_host_budget=2)
        for f in p.fetch:
            last[f.url] = float(run)
            seen.append(f.url)
    assert set(seen) == {f.url for f in M}
