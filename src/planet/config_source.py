"""Where a run's config comes from: a URL when one is set, else the image.

config.ini is edited on GitHub, so the job downloads it at the start of each
run, the way the old EC2 cron job did a `git pull`. Any failure (network,
HTTP error, a file that doesn't parse or lists no feeds) falls back to the
config.ini built into the image, so a bad edit can't stop the site updating.
"""

from __future__ import annotations

import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from planet.config import Config, load, parse
from planet.fetch import DEFAULT_USER_AGENT

log = logging.getLogger(__name__)

TIMEOUT_S = 10.0
MAX_BYTES = 5 * 1024 * 1024  # config.ini is ~300 KB


class Source(StrEnum):
    URL = "url"
    IMAGE = "image"
    # A URL was set but was unusable; the image copy was used instead.
    FALLBACK = "fallback"


@dataclass(frozen=True)
class Resolved:
    config: Config
    source: Source


class ConfigError(Exception):
    pass


def download(url: str, timeout_s: float = TIMEOUT_S, max_bytes: int = MAX_BYTES) -> str:
    if not url.startswith(("https://", "http://")):
        raise ConfigError(f"not an http(s) URL: {url}")
    # S310 (file:// and other schemes): checked above. HTTP errors raise HTTPError.
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        body: bytes = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ConfigError(f"larger than {max_bytes} bytes")
    return body.decode("utf-8")


def parse_checked(text: str) -> Config:
    """Parse, rejecting a config that would empty the planet."""
    config = parse(text)
    if not config.feeds:
        raise ConfigError("no feeds")
    return config


def resolve(
    url: str | None,
    image_path: Path,
    fetch: Callable[[str], str] = download,
) -> Resolved:
    if not url:
        return Resolved(load(image_path), Source.IMAGE)
    try:
        return Resolved(parse_checked(fetch(url)), Source.URL)
    except Exception as e:  # noqa: BLE001 - any failure means: use the image copy
        log.error("config: %s unusable (%s: %s); using the image copy", url, type(e).__name__, e)
        return Resolved(load(image_path), Source.FALLBACK)
