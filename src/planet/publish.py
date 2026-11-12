"""S3 I/O: the cache object and the published site.

Nothing here knows about feeds; it moves files.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger("planet")

PAGE_CACHE_CONTROL = "public, max-age=300"  # index.html, atom.xml
STATIC_CACHE_CONTROL = "public, max-age=86400"  # css, images, js
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".xml": "application/atom+xml; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
}


class CacheConflict(Exception):
    """The cache object changed since we read it (an overlapping run)."""


def _error_code(e: ClientError) -> str:
    return e.response.get("Error", {}).get("Code", "")


def pull_cache(s3: S3Client, bucket: str, key: str, path: Path) -> str | None:
    """Download the cache to `path`. Returns its ETag, or None if it doesn't
    exist yet (first run: start with an empty cache)."""
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if _error_code(e) in ("NoSuchKey", "404"):
            log.warning("no cache at s3://%s/%s; starting empty", bucket, key)
            return None
        raise
    with path.open("wb") as f:
        for chunk in resp["Body"].iter_chunks(1024 * 1024):
            f.write(chunk)
    return resp["ETag"]


def push_cache(s3: S3Client, bucket: str, key: str, path: Path, etag: str | None) -> None:
    """Upload the cache, only if nobody replaced it since `pull_cache`."""
    try:
        with path.open("rb") as f:
            if etag:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    IfMatch=etag,
                    ContentType="application/vnd.sqlite3",
                )
            else:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    IfNoneMatch="*",
                    ContentType="application/vnd.sqlite3",
                )
    except ClientError as e:
        if _error_code(e) in ("PreconditionFailed", "ConditionalRequestConflict", "412"):
            raise CacheConflict(f"s3://{bucket}/{key} changed during the run") from e
        raise


def _content_type(path: Path) -> str:
    return (
        CONTENT_TYPES.get(path.suffix)
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def _md5_etag(path: Path) -> str:
    return '"' + hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest() + '"'


def _remote_etags(s3: S3Client, bucket: str, prefix: str) -> dict[str, str]:
    etags: dict[str, str] = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if (k := obj.get("Key")) and (etag := obj.get("ETag")):
                etags[k] = etag
    return etags


def publish_site(s3: S3Client, bucket: str, site_dir: Path) -> dict[str, int]:
    """Upload `site_dir` to the bucket root.

    Static files go first and are skipped when unchanged; the pages go last
    (atom.xml, then index.html), so a page never points at a missing asset.
    Nothing is deleted: removed static files linger harmlessly.
    """
    files = sorted(p for p in site_dir.rglob("*") if p.is_file())
    pages = [site_dir / "atom.xml", site_dir / "index.html"]
    static = [p for p in files if p not in pages]
    remote = _remote_etags(s3, bucket, "static/")

    uploaded = skipped = 0
    for path in static:
        key = path.relative_to(site_dir).as_posix()
        if remote.get(key) == _md5_etag(path):
            skipped += 1
            continue
        s3.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": _content_type(path), "CacheControl": STATIC_CACHE_CONTROL},
        )
        uploaded += 1
    for path in pages:
        if path.exists():
            s3.upload_file(
                str(path),
                bucket,
                path.name,
                ExtraArgs={"ContentType": _content_type(path), "CacheControl": PAGE_CACHE_CONTROL},
            )
            uploaded += 1
    return {"uploaded": uploaded, "skipped": skipped}
