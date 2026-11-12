"""One run: sync subscriptions -> fetch -> merge -> prune -> render -> write.

Works only with local paths. The Lambda handler (handler.py) moves the cache
and the output to and from S3 around this.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from planet import config as config_mod
from planet.assets import stylesheet
from planet.config import Config, Feed
from planet.fetch import (
    Deferred,
    Download,
    Failed,
    Fetched,
    FetchOptions,
    FetchRequest,
    NotModified,
    fetch_all,
)
from planet.filtering import keep
from planet.model import ParsedFeed
from planet.parse import parse_feed
from planet.render import render
from planet.sanitize import sanitize_entry
from planet.schedule import DEFAULT_PER_HOST_BUDGET, plan
from planet.store import Store
from planet.translations import one_per_post

log = logging.getLogger("planet")

KEEP_PER_FEED = 10
# Static source files that aren't served (Compass/Sass sources).
# style.css is published hashed (planet.assets), not as is.
STATIC_IGNORE = shutil.ignore_patterns("style.css")


@dataclass(frozen=True)
class RunStats:
    feeds: int
    ok: int
    not_modified: int
    errors: int
    # over their host's budget, rate limited, or cut off by the deadline;
    # their state is left as is
    deferred: int
    backing_off: int  # failing feeds not due for another attempt yet
    entries_stored: int
    pruned: int
    items_rendered: int
    fetch_s: float
    total_s: float


def prepare(feed: Feed, download: Download) -> ParsedFeed:
    """Parse, keep one language version of each post, sanitize, then apply
    the feed's filter (Venus filtered the scrubbed entry too). Runs in a
    worker thread."""
    parsed = parse_feed(download.content, feed.url, download.content_type)
    posts = one_per_post(parsed.entries)
    entries = tuple(e for e in map(sanitize_entry, posts.kept) if keep(feed, e))
    return ParsedFeed(meta=parsed.meta, entries=entries, dropped_translations=posts.dropped)


def write_site(out_dir: Path, files: dict[str, str], static_dir: Path | None) -> None:
    """`files`: {path relative to the site root: content}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if static_dir:
        shutil.copytree(static_dir, out_dir / "static", dirs_exist_ok=True, ignore=STATIC_IGNORE)
    for name, content in files.items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def run(
    cfg: Config,
    store: Store,
    out_dir: Path,
    static_dir: Path | None,
    *,
    now: float,
    deadline: float | None,
    options: FetchOptions,
    per_host_budget: int = DEFAULT_PER_HOST_BUDGET,
) -> RunStats:
    start = time.monotonic()
    store.sync_subscriptions(cfg.feeds)

    feeds_by_url = {f.url: f for f in cfg.feeds}
    todo = plan(cfg.feeds, store.last_fetched(), store.backing_off(now), per_host_budget)
    if todo.over_budget:
        log.info("deferred %d feeds over their host's budget", len(todo.over_budget))
    requests = [FetchRequest(f.url, *store.validators(f.url)) for f in todo.fetch]
    results = asyncio.run(
        fetch_all(requests, lambda d: prepare(feeds_by_url[d.url], d), options, deadline)
    )
    fetch_s = time.monotonic() - start

    stored = ok = not_modified = failed = 0
    deferred = len(todo.over_budget)
    for r in results:
        match r:
            case Fetched(url=url, value=parsed, etag=etag, last_modified=lm):
                store.record_success(url, parsed.meta, etag, lm, now)
                store.upsert_entries(url, parsed.entries, now)
                store.delete_entries(url, parsed.dropped_translations)
                stored += len(parsed.entries)
                ok += 1
            case NotModified(url=url, etag=etag, last_modified=lm):
                store.record_not_modified(url, etag, lm, now)
                not_modified += 1
            case Failed(url=url, error=error):
                retry_at = store.record_error(url, error, now)
                log.info(
                    "feed error: %s: %s (next attempt in %.0fh)",
                    url,
                    error,
                    (retry_at - now) / 3600,
                )
                failed += 1
            case Deferred(url=url, reason=reason):
                log.info("feed deferred: %s: %s", url, reason)
                deferred += 1
    pruned = store.prune(KEEP_PER_FEED)
    store.commit()

    s = cfg.settings
    items = store.select_items(limit=s.items_per_page, per_feed=s.new_feed_items)
    css = stylesheet(static_dir)
    pages = render(s, items, store.channels(), now, stylesheet=css.href)
    write_site(out_dir, {**pages, css.path: css.content}, static_dir)

    return RunStats(
        feeds=len(cfg.feeds),
        ok=ok,
        not_modified=not_modified,
        errors=failed,
        deferred=deferred,
        backing_off=len(todo.backing_off),
        entries_stored=stored,
        pruned=pruned,
        items_rendered=len(items),
        fetch_s=round(fetch_s, 1),
        total_s=round(time.monotonic() - start, 1),
    )


def cli() -> None:
    ap = argparse.ArgumentParser(description="Run Planet Clojure once, locally.")
    ap.add_argument("--config", default="config.ini", type=Path)
    ap.add_argument("--cache", default="local/cache.sqlite", type=Path)
    ap.add_argument("--out", default="local/output", type=Path)
    ap.add_argument("--static", default="static", type=Path)
    ap.add_argument("--concurrency", type=int, default=FetchOptions.concurrency)
    ap.add_argument(
        "--max-fetch-seconds", type=float, default=600, help="global deadline for the fetch phase"
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = config_mod.load(args.config)
    options = FetchOptions(concurrency=args.concurrency, timeout_s=float(cfg.settings.feed_timeout))
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    store = Store.open(args.cache)
    try:
        stats = run(
            cfg,
            store,
            args.out,
            args.static,
            now=time.time(),
            deadline=time.monotonic() + args.max_fetch_seconds,
            options=options,
        )
    finally:
        store.close()
    print(stats)


if __name__ == "__main__":
    cli()
