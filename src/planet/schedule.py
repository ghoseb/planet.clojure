"""Which feeds to request in a run.

Feeds that are backing off (see backoff.py) are left out. The rest are
grouped by host, and each host gets at most `per_host_budget` requests per
run. Medium, which serves ~60 of our feeds, answers 429 after about 22 quick
requests from one address, so without a budget the same feeds would use up
its allowance every run and the rest would never refresh. Within a host, the
feeds fetched longest ago (never-fetched first) go first, so the ones left
over this run are first in line for the next.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from planet.config import Feed
from planet.fetch import host_of

DEFAULT_PER_HOST_BUDGET = 20


@dataclass(frozen=True)
class Plan:
    fetch: tuple[Feed, ...]  # to request this run
    over_budget: tuple[Feed, ...]  # due, but their host's budget is used up
    backing_off: tuple[Feed, ...]  # not due yet


def plan(
    feeds: Sequence[Feed],
    last_fetched: Mapping[str, float | None],
    backing_off: Collection[str],
    per_host_budget: int = DEFAULT_PER_HOST_BUDGET,
) -> Plan:
    by_host: dict[str, list[Feed]] = {}
    waiting: list[Feed] = []
    for feed in feeds:
        if feed.url in backing_off:
            waiting.append(feed)
        else:
            by_host.setdefault(host_of(feed.url), []).append(feed)

    def fetched_at(feed: Feed) -> float:
        when = last_fetched.get(feed.url)
        return float("-inf") if when is None else when

    fetch: list[Feed] = []
    over: list[Feed] = []
    for host_feeds in by_host.values():
        # sorted() is stable: ties keep config order.
        ranked = sorted(host_feeds, key=fetched_at)
        fetch += ranked[:per_host_budget]
        over += ranked[per_host_budget:]
    return Plan(tuple(fetch), tuple(over), tuple(waiting))
