import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from conftest import FeedServer
from planet.fetch import (
    RATE_LIMITED,
    Deferred,
    Download,
    Failed,
    Fetched,
    FetchOptions,
    FetchRequest,
    FetchResult,
    NotModified,
    fetch_all,
    host_of,
    retry_after_s,
)

FAST = FetchOptions(timeout_s=1.0, max_bytes=1_000_000, host_interval_s=0)


def body_len(download: Download) -> int:
    return len(download.content)


def run(
    requests: Sequence[FetchRequest],
    process: Callable[[Download], int] = body_len,
    options: FetchOptions = FAST,
    deadline: float | None = None,
) -> list[FetchResult[int]]:
    return asyncio.run(fetch_all(requests, process, options, deadline))


def error_of(result: FetchResult[int]) -> str:
    assert isinstance(result, Failed), result
    return result.error


def test_ok_records_validators_and_processes_body(server: FeedServer) -> None:
    (r,) = run([FetchRequest(server.url("/rss.xml"))])
    assert isinstance(r, Fetched)
    assert r.etag == '"v1"'
    assert r.value > 100


def test_process_gets_the_content_type(server: FeedServer) -> None:
    def content_type(download: Download) -> str | None:
        return download.content_type

    (r,) = asyncio.run(fetch_all([FetchRequest(server.url("/atom.xml"))], content_type, FAST))
    assert isinstance(r, Fetched)
    assert r.value == "application/atom+xml"


def test_conditional_get_returns_not_modified(server: FeedServer) -> None:
    (r,) = run([FetchRequest(server.url("/rss.xml"), etag='"v1"')])
    assert r == NotModified(server.url("/rss.xml"), etag='"v1"', last_modified=None)


def test_total_timeout_catches_hangs_and_slow_drips(server: FeedServer) -> None:
    start = time.monotonic()
    hang, drip = run([FetchRequest(server.url("/hang")), FetchRequest(server.url("/drip"))])
    assert "timed out" in error_of(hang)
    # /drip sends headers + a byte every 0.1s: a read timeout would never fire
    assert "timed out" in error_of(drip)
    assert time.monotonic() - start < 3


def test_size_cap(server: FeedServer) -> None:
    (r,) = run([FetchRequest(server.url("/big"))])
    assert "larger than" in error_of(r)


def test_http_errors_and_bad_urls(server: FeedServer) -> None:
    missing, bad = run([FetchRequest(server.url("/missing")), FetchRequest("typo://nowhere/feed")])
    assert error_of(missing) == "HTTP 404"
    assert error_of(bad)


def test_process_errors_are_isolated(server: FeedServer) -> None:
    def process(download: Download) -> int:
        if download.url.endswith("rss.xml"):
            raise ValueError("bad feed")
        return 1

    ok, broken = run(
        [FetchRequest(server.url("/atom.xml")), FetchRequest(server.url("/rss.xml"))],
        process=process,
    )
    assert isinstance(ok, Fetched)
    assert "bad feed" in error_of(broken)


def test_deadline_cancels_stragglers_and_keeps_order(server: FeedServer) -> None:
    start = time.monotonic()
    # different hosts: same-host requests would queue behind /hang
    hang, atom = run(
        [
            FetchRequest(server.url("/hang")),
            FetchRequest(server.url("/atom.xml", host="localhost")),
        ],
        options=FetchOptions(timeout_s=30),
        deadline=time.monotonic() + 0.5,
    )
    assert time.monotonic() - start < 2
    # not the feed's fault, so not a failure
    assert hang == Deferred(server.url("/hang"), "cancelled at run deadline")
    assert isinstance(atom, Fetched)


def test_one_request_per_host_at_a_time_hosts_in_parallel(server: FeedServer) -> None:
    requests = [
        FetchRequest(server.url(f"/slow?i={i}", host=h))
        for i in range(4)
        for h in ("127.0.0.1", "localhost")
    ]
    start = time.monotonic()
    results = run(requests, options=FetchOptions(timeout_s=5, host_interval_s=0))
    elapsed = time.monotonic() - start
    assert all(isinstance(r, Fetched) for r in results)
    assert server.peak == {"127.0.0.1": 1, "localhost": 1}
    assert 0.8 <= elapsed < 1.4  # 4 x 0.2s per host, the two hosts overlap


def test_requests_to_one_host_start_spaced_apart(server: FeedServer) -> None:
    requests = [FetchRequest(server.url(f"/stamp?i={i}")) for i in range(3)]
    run(requests, options=FetchOptions(timeout_s=2, host_interval_s=0.3))
    a, b, c = server.starts["/stamp"][-3:]
    assert b - a >= 0.28 and c - b >= 0.28


def test_429_pauses_the_host_for_retry_after_capped_then_retries(server: FeedServer) -> None:
    # /limited-once sends Retry-After: 1; the cap shortens the pause to 0.4s
    options = FetchOptions(timeout_s=2, host_interval_s=0, rate_limit_pause_s=0, max_pause_s=0.4)
    start = time.monotonic()
    (r,) = run([FetchRequest(server.url("/limited-once?t=retry"))], options=options)
    elapsed = time.monotonic() - start
    assert isinstance(r, Fetched)
    assert server.hits["/limited-once?t=retry"] == 2
    assert 0.38 <= elapsed < 0.9


def test_second_429_defers_the_rest_of_the_host(server: FeedServer) -> None:
    paths = [f"/always-429?t=defer&i={i}" for i in range(4)]
    options = FetchOptions(timeout_s=2, host_interval_s=0, rate_limit_pause_s=0.1)
    results = run(
        [
            *(FetchRequest(server.url(p)) for p in paths),
            FetchRequest(server.url("/atom.xml", "localhost")),
        ],
        options=options,
    )
    assert results[:4] == [Deferred(server.url(p), RATE_LIMITED) for p in paths]
    assert isinstance(results[4], Fetched)  # other hosts are unaffected
    # one 429, a pause, a second 429: then no more requests to that host
    assert sum(server.hits.get(p, 0) for p in paths) == 2


def test_retry_after_s() -> None:
    now = datetime(2026, 11, 12, 7, 0, 0, tzinfo=UTC)
    assert retry_after_s("120") == 120.0
    assert retry_after_s("Thu, 12 Nov 2026 07:02:00 GMT", now) == 120.0
    assert retry_after_s("Thu, 12 Nov 2026 06:00:00 GMT", now) == 0.0  # in the past
    assert retry_after_s("soon") is None
    assert retry_after_s(None) is None


def test_host_of() -> None:
    assert host_of("https://Medium.com/feed/@x") == "medium.com"
    assert host_of("https://a.medium.com/feed") == "a.medium.com"
    assert host_of("typo://nowhere/feed") == "nowhere"


def test_empty() -> None:
    assert run([]) == []
