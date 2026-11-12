"""Throwaway: time a full fetch + parse of every feed in config.ini.

Answers "will a run fit comfortably inside Lambda's 15-minute limit?" with
real numbers instead of estimates. Single pass, no conditional GET (a cold
cache is the worst case for a normal run).

    uv run scripts/measure.py [--config config.ini]
                              [--concurrency 75] [--per-host 6]
                              [--timeout 15] [--max-bytes 5000000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import feedparser

from planet.config import load

USER_AGENT = "PlanetClojure/2.0 (+http://planet.clojure.in/)"


@dataclass
class Result:
    url: str
    host: str
    status: int | None = None
    error: str | None = None
    fetch_s: float = 0.0
    bytes: int = 0
    has_etag: bool = False
    has_last_modified: bool = False
    parse_s: float = 0.0
    entries: int = 0
    bozo: bool = False


class TooLarge(Exception):
    pass


async def fetch_one(session, sem, url, timeout_s, max_bytes):
    result = Result(url=url, host=urlsplit(url).hostname or "?")
    body = b""
    async with sem:
        start = time.monotonic()
        try:
            # One total limit around the whole request: DNS, connect,
            # headers and body. Catches slow-drip servers too.
            async with asyncio.timeout(timeout_s):
                async with session.get(url) as resp:
                    result.status = resp.status
                    result.has_etag = "ETag" in resp.headers
                    result.has_last_modified = "Last-Modified" in resp.headers
                    chunks = []
                    size = 0
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise TooLarge(f">{max_bytes} bytes")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    result.bytes = size
        except TimeoutError:
            result.error = "timeout"
        except TooLarge as e:
            result.error = f"too_large {e}"
        except Exception as e:  # noqa: BLE001 - measurement: record everything
            result.error = f"{type(e).__name__}: {e}"[:200]
        result.fetch_s = time.monotonic() - start
    return result, body


async def fetch_all(urls, concurrency, per_host, timeout_s, max_bytes):
    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=per_host, ttl_dns_cache=300)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        return await asyncio.gather(
            *(fetch_one(session, sem, u, timeout_s, max_bytes) for u in urls)
        )


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, round(p / 100 * (len(values) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.ini")
    ap.add_argument("--concurrency", type=int, default=75)
    ap.add_argument("--per-host", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--max-bytes", type=int, default=5_000_000)
    args = ap.parse_args()

    feeds = load(args.config).feeds
    urls = [f.url for f in feeds]
    print(
        f"{len(urls)} feeds, concurrency={args.concurrency}, "
        f"per_host={args.per_host}, timeout={args.timeout}s"
    )

    t0 = time.monotonic()
    pairs = asyncio.run(
        fetch_all(urls, args.concurrency, args.per_host, args.timeout, args.max_bytes)
    )
    fetch_wall = time.monotonic() - t0

    t1 = time.monotonic()
    for result, body in pairs:
        if body and result.status == 200:
            p0 = time.monotonic()
            parsed = feedparser.parse(body)
            result.parse_s = time.monotonic() - p0
            result.entries = len(parsed.entries)
            result.bozo = bool(parsed.bozo)
    parse_wall = time.monotonic() - t1

    results = [r for r, _ in pairs]
    ok = [r for r in results if r.status == 200 and not r.error]
    fetch_times = [r.fetch_s for r in results]
    parse_times = [r.parse_s for r in results if r.parse_s]

    print(f"\nfetch wall time : {fetch_wall:6.1f}s")
    print(f"parse wall time : {parse_wall:6.1f}s  (sequential, single thread)")
    print(f"total           : {fetch_wall + parse_wall:6.1f}s")
    print(
        f"\nper-feed fetch  : p50={pct(fetch_times, 50):.2f}s "
        f"p95={pct(fetch_times, 95):.2f}s p99={pct(fetch_times, 99):.2f}s "
        f"max={max(fetch_times):.2f}s"
    )
    if parse_times:
        print(
            f"per-feed parse  : p50={pct(parse_times, 50) * 1000:.0f}ms "
            f"p95={pct(parse_times, 95) * 1000:.0f}ms "
            f"max={max(parse_times) * 1000:.0f}ms "
            f"mean={statistics.mean(parse_times) * 1000:.0f}ms"
        )
    print(f"\nOK (200)        : {len(ok)}")
    print(f"  with ETag     : {sum(r.has_etag for r in ok)}")
    print(f"  with Last-Mod : {sum(r.has_last_modified for r in ok)}")
    print(f"  either        : {sum(r.has_etag or r.has_last_modified for r in ok)}")
    print(f"  0 entries     : {sum(1 for r in ok if r.entries == 0)}")
    print(f"total bytes     : {sum(r.bytes for r in results) / 1e6:.1f} MB")

    print("\nstatus / error breakdown:")
    kinds = Counter(
        r.error.split(":")[0].split(" ")[0] if r.error else f"HTTP {r.status}" for r in results
    )
    for kind, n in kinds.most_common():
        print(f"  {n:4d}  {kind}")

    print("\nslowest 15 feeds:")
    for r in sorted(results, key=lambda r: r.fetch_s, reverse=True)[:15]:
        print(f"  {r.fetch_s:6.2f}s  {r.status or '-':>4}  {r.error or ''}  {r.url}")

    print("\nslowest 5 parses:")
    for r in sorted(results, key=lambda r: r.parse_s, reverse=True)[:5]:
        print(f"  {r.parse_s * 1000:6.0f}ms  {r.bytes / 1e3:7.0f}KB  {r.url}")

    print("\nbusiest hosts:")
    for host, n in Counter(r.host for r in results).most_common(5):
        print(f"  {n:4d}  {host}")

    out = Path("local") / f"measure-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "args": vars(args),
                "fetch_wall_s": fetch_wall,
                "parse_wall_s": parse_wall,
                "results": [asdict(r) for r in results],
            },
            indent=1,
        )
    )
    print(f"\nfull results: {out}")


if __name__ == "__main__":
    main()
