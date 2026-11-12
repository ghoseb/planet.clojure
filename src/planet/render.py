"""Render the static pages from selected items and channels."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import cast

import jinja2

from planet.config import Settings
from planet.model import Channel, Item
from planet.sanitize import plain_text

GENERATOR = "planet.clojure v2"
GENERATOR_URI = "https://github.com/ghoseb/planet.clojure"

# template -> output file name
PAGES = {"index.html.j2": "index.html", "atom.xml.j2": "atom.xml"}


def _utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


def _date(ts: float, fmt: str) -> str:
    return _utc(ts).strftime(fmt)


def _iso(ts: float) -> str:
    return _utc(ts).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _environment() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("planet", "templates"),
        autoescape=True,  # titles/names are plain text; content is |safe-d explicitly
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    # jinja2 types `filters` from its built-ins; custom filters need the cast.
    filters = cast("dict[str, Callable[..., str]]", env.filters)
    filters.update(date=_date, iso=_iso, plain=plain_text)
    return env


def render(
    settings: Settings, items: Sequence[Item], channels: Sequence[Channel], now: float
) -> dict[str, str]:
    """Returns {output file name: content}."""
    env = _environment()
    context = {
        "name": settings.name,
        "link": settings.link,
        "feed": settings.feed,
        "generator": GENERATOR,
        "generator_uri": GENERATOR_URI,
        "date_format": settings.date_format,
        "now": now,
        "items": items,
        "channels": channels,
    }
    return {out: env.get_template(tpl).render(context) for tpl, out in PAGES.items()}
