"""Concurrent HTTP fetching with hard time limits.

- Bounded concurrency overall, and at most `per_host` (default 1) requests
  in flight to any one host, so a host serving many feeds (medium.com has
  ~60) sees them one after another instead of as a burst.
- One *total* time limit per URL covering DNS, connect, headers and body, so
  a server that trickles bytes can't hold a slot forever.
- Conditional GET (If-None-Match / If-Modified-Since).
- Response size cap.
- A global deadline: whatever hasn't finished by then is cancelled and
  reported as an error, so a run always completes.
- Each body is handed to `process(Download)` in a worker thread as soon as
  it arrives, so CPU work (parsing) overlaps with the remaining downloads and
  bodies don't pile up in memory.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp

DEFAULT_USER_AGENT = "PlanetClojure/2.0 (+https://planet.clojure.in/)"
ACCEPT = (
    "application/atom+xml, application/rss+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.8"
)


@dataclass(frozen=True)
class FetchRequest:
    url: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class FetchOptions:
    concurrency: int = 75
    per_host: int = 1
    timeout_s: float = 15.0
    max_bytes: int = 20_000_000
    user_agent: str = DEFAULT_USER_AGENT
    # Threads running `process`. Parsing is pure Python (GIL-bound), so more
    # threads add contention, not throughput.
    process_workers: int = 2


@dataclass(frozen=True)
class Download:
    """A 2xx response body, as handed to `process`."""

    url: str
    content: bytes
    content_type: str | None  # the Content-Type header, charset included


@dataclass(frozen=True)
class Fetched[T]:
    """200: the body was downloaded and processed into `value`."""

    url: str
    value: T
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class NotModified:
    """304: the validators to keep for the next conditional GET."""

    url: str
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class Failed:
    url: str
    error: str


type FetchResult[T] = Fetched[T] | NotModified | Failed


@dataclass(frozen=True)
class _Response:
    status: int
    etag: str | None
    last_modified: str | None
    content_type: str | None
    body: bytes | None  # None unless 2xx


class _TooLargeError(Exception):
    pass


def _describe(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"[:300]


async def _download(
    session: aiohttp.ClientSession, request: FetchRequest, options: FetchOptions
) -> _Response:
    """Raises on network failure, timeout or an oversized body."""
    headers: dict[str, str] = {}
    if request.etag:
        headers["If-None-Match"] = request.etag
    if request.last_modified:
        headers["If-Modified-Since"] = request.last_modified
    async with (
        asyncio.timeout(options.timeout_s),
        session.get(request.url, headers=headers) as resp,
    ):
        etag = resp.headers.get("ETag")
        last_modified = resp.headers.get("Last-Modified")
        content_type = resp.headers.get("Content-Type")
        if not 200 <= resp.status < 300:
            return _Response(resp.status, etag, last_modified, content_type, None)
        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > options.max_bytes:
                raise _TooLargeError(f"response larger than {options.max_bytes} bytes")
            chunks.append(chunk)
        return _Response(resp.status, etag, last_modified, content_type, b"".join(chunks))


def host_of(url: str) -> str:
    """The key requests are serialized on: the lower-cased host name."""
    try:
        return (urlsplit(url).hostname or url).lower()
    except ValueError:
        return url


async def _fetch_one[T](
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    host_sem: asyncio.Semaphore,
    executor: ThreadPoolExecutor,
    request: FetchRequest,
    process: Callable[[Download], T],
    options: FetchOptions,
) -> FetchResult[T]:
    url = request.url
    # Host first, then a global slot: requests queued behind a busy host
    # don't hold global slots that other hosts could use.
    async with host_sem, sem:
        try:
            resp = await _download(session, request, options)
        except TimeoutError:
            return Failed(url, f"timed out after {options.timeout_s:g}s")
        except _TooLargeError as e:
            return Failed(url, str(e))
        except Exception as e:  # noqa: BLE001 -- any network failure is per feed
            return Failed(url, _describe(e))

    # Slots released: processing doesn't hold up downloads.
    if resp.status == 304:
        return NotModified(
            url, resp.etag or request.etag, resp.last_modified or request.last_modified
        )
    if resp.body is None:
        return Failed(url, f"HTTP {resp.status}")
    try:
        loop = asyncio.get_running_loop()
        download = Download(url, resp.body, resp.content_type)
        value = await loop.run_in_executor(executor, process, download)
    except Exception as e:  # noqa: BLE001 -- a broken feed must not stop the run
        return Failed(url, _describe(e))
    return Fetched(url, value, resp.etag, resp.last_modified)


async def fetch_all[T](
    requests: Sequence[FetchRequest],
    process: Callable[[Download], T],
    options: FetchOptions | None = None,
    deadline: float | None = None,
) -> list[FetchResult[T]]:
    """Fetch every request; results are in request order.

    `deadline` is a `time.monotonic()` value. Requests still running then are
    cancelled and reported as failed.
    """
    if not requests:
        return []
    options = options or FetchOptions()
    sem = asyncio.Semaphore(options.concurrency)
    host_sems: defaultdict[str, asyncio.Semaphore] = defaultdict(
        lambda: asyncio.Semaphore(options.per_host)
    )
    connector = aiohttp.TCPConnector(
        limit=options.concurrency, limit_per_host=options.per_host, ttl_dns_cache=300
    )
    headers = {"User-Agent": options.user_agent, "Accept": ACCEPT}
    with ThreadPoolExecutor(max_workers=options.process_workers) as executor:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            tasks = [
                asyncio.create_task(
                    _fetch_one(
                        session, sem, host_sems[host_of(r.url)], executor, r, process, options
                    )
                )
                for r in requests
            ]
            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    return [
        Failed(request.url, "cancelled at run deadline") if task.cancelled() else task.result()
        for request, task in zip(requests, tasks, strict=True)
    ]
