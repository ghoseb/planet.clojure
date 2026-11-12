"""AWS Lambda entry point: S3 cache in -> one run -> site and cache out to S3.

Environment:
  SITE_BUCKET     bucket served by CloudFront (required)
  CACHE_BUCKET    private bucket holding the cache (required)
  CACHE_KEY       default "planet/cache.sqlite"
  CONFIG_PATH     default "config.ini" (relative to the task root)
  STATIC_DIR      default "static"
  RESERVE_SECONDS time kept back from the fetch deadline for merge, render
                  and upload; default 120
  AWS_ENDPOINT_URL  set locally to point boto3 at floci
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import resource
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3

from planet import config as config_mod
from planet.fetch import FetchOptions
from planet.main import run
from planet.publish import publish_site, pull_cache, push_cache
from planet.store import Store

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger("planet")
log.setLevel(logging.INFO)

TASK_ROOT = Path(os.environ.get("LAMBDA_TASK_ROOT", "."))


def _path(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else TASK_ROOT / p


def _compact(path: Path) -> None:
    """Reclaim pages freed by pruning so the uploaded object stays small."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


class LambdaContext(Protocol):
    """The part of the Lambda context object we use."""

    def get_remaining_time_in_millis(self) -> int: ...


def handler(_event: object, context: LambdaContext) -> dict[str, int | float]:
    site_bucket = os.environ["SITE_BUCKET"]
    cache_bucket = os.environ["CACHE_BUCKET"]
    cache_key = os.environ.get("CACHE_KEY", "planet/cache.sqlite")
    reserve_s = float(os.environ.get("RESERVE_SECONDS", "120"))

    remaining_s = context.get_remaining_time_in_millis() / 1000
    deadline = time.monotonic() + max(30.0, remaining_s - reserve_s)

    cfg = config_mod.load(_path("CONFIG_PATH", "config.ini"))
    s3: S3Client = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        cache_path, out_dir = work / "cache.sqlite", work / "site"

        etag = pull_cache(s3, cache_bucket, cache_key, cache_path)
        store = Store.open(cache_path)
        try:
            stats = run(
                cfg,
                store,
                out_dir,
                _path("STATIC_DIR", "static"),
                now=time.time(),
                deadline=deadline,
                options=FetchOptions(timeout_s=float(cfg.settings.feed_timeout)),
            )
        finally:
            store.close()
        _compact(cache_path)

        # Site first: if the cache push then fails, the next run simply
        # refetches; the reverse order could publish nothing new for a run.
        published = publish_site(s3, site_bucket, out_dir)
        push_cache(s3, cache_bucket, cache_key, cache_path, etag)

        result = {
            **dataclasses.asdict(stats),
            **published,
            "cache_bytes": cache_path.stat().st_size,
            # ru_maxrss is KiB on Linux
            "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
        }
    log.info("run complete %s", json.dumps(result))
    return result
