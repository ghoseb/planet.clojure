from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

from planet.publish import CacheConflict, publish_site, pull_cache, push_cache

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@pytest.fixture
def s3() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3", region_name="us-east-1"
        )
        client.create_bucket(Bucket="cache")
        client.create_bucket(Bucket="site")
        yield client


def test_cache_round_trip_with_conditional_put(s3: S3Client, tmp_path: Path) -> None:
    local = tmp_path / "cache.sqlite"
    assert pull_cache(s3, "cache", "k", local) is None  # first run

    local.write_bytes(b"v1")
    push_cache(s3, "cache", "k", local, etag=None)
    etag = pull_cache(s3, "cache", "k", tmp_path / "copy")
    assert (tmp_path / "copy").read_bytes() == b"v1"

    local.write_bytes(b"v2")
    push_cache(s3, "cache", "k", local, etag=etag)
    assert s3.get_object(Bucket="cache", Key="k")["Body"].read() == b"v2"


def test_overlapping_run_is_rejected(s3: S3Client, tmp_path: Path) -> None:
    local = tmp_path / "cache.sqlite"
    local.write_bytes(b"v1")
    push_cache(s3, "cache", "k", local, etag=None)
    stale = pull_cache(s3, "cache", "k", local)

    local.write_bytes(b"other run")
    push_cache(s3, "cache", "k", local, etag=stale)
    with pytest.raises(CacheConflict):
        push_cache(s3, "cache", "k", local, etag=stale)
    with pytest.raises(CacheConflict):  # first-run race too
        push_cache(s3, "cache", "k", local, etag=None)


def test_publish_site_types_and_skips_unchanged_static(s3: S3Client, tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "static" / "css").mkdir(parents=True)
    (site / "index.html").write_text("<html></html>")
    (site / "atom.xml").write_text("<feed/>")
    (site / "static" / "css" / "screen.css").write_text("body{}")

    assert publish_site(s3, "site", site) == {"uploaded": 3, "skipped": 0}
    head = s3.head_object(Bucket="site", Key="index.html")
    assert head["ContentType"] == "text/html; charset=utf-8"
    assert head["CacheControl"] == "public, max-age=300"
    css = s3.head_object(Bucket="site", Key="static/css/screen.css")
    assert css["ContentType"] == "text/css; charset=utf-8"

    assert publish_site(s3, "site", site) == {"uploaded": 2, "skipped": 1}
