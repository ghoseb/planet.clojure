"""Render the static pages from selected items and channels."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import jinja2

from planet.collapse import split
from planet.config import Settings
from planet.highlight import highlight_blocks
from planet.model import Channel, Item
from planet.repeated_title import drop_repeated_title
from planet.sanitize import plain_text

GENERATOR = "planet.clojure v2"
GENERATOR_URI = "https://github.com/ghoseb/planet.clojure"

# template -> output file name
PAGES = {"index.html.j2": "index.html", "atom.xml.j2": "atom.xml"}


@dataclass(frozen=True)
class Shown:
    """An item as the home page shows it: without a repeated title,
    highlighted, maybe collapsed."""

    item: Item
    visible: str
    more: str | None


def shown(item: Item) -> Shown:
    parts = split(highlight_blocks(drop_repeated_title(item.content, item.title)))
    return Shown(item, parts.visible, parts.more)


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
    settings: Settings,
    items: Sequence[Item],
    channels: Sequence[Channel],
    now: float,
    *,
    stylesheet: str,
) -> dict[str, str]:
    """Returns {output file name: content}. `stylesheet` is the CSS URL.

    The Atom feed carries entries as stored; only the home page highlights
    code and collapses long entries (feed readers have their own styles).
    """
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
        "entries": [shown(item) for item in items],
        "stylesheet": stylesheet,
        "channels": channels,
    }
    return {out: env.get_template(tpl).render(context) for tpl, out in PAGES.items()}
