"""Parse config.ini into plain data.

The format is Venus's: a [Planet] section of site settings, and one section
per feed named after its URL. Unknown keys (e.g. the `twitter` many feed
sections still carry) are ignored rather than rejected.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

PLANET_SECTION = "Planet"


@dataclass(frozen=True)
class Feed:
    url: str
    name: str
    # Every pattern must match an entry's readable text for the entry to be
    # kept (Venus `filter` semantics: case-sensitive re.search).
    filters: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True)
class Settings:
    name: str
    link: str
    # URL of the planet's own Atom feed (self link / id in atom.xml).
    feed: str
    feed_timeout: int
    # Max items on a rendered page.
    items_per_page: int
    # Max items any single feed may contribute to a rendered page (0 = no
    # cap). Venus applied this in splice, despite the option's name.
    new_feed_items: int
    date_format: str


@dataclass(frozen=True)
class Config:
    settings: Settings
    feeds: tuple[Feed, ...]


def _unquote(value: str) -> str:
    """Strip one pair of surrounding double quotes.

    Some contributors quote names containing apostrophes, e.g.
    `name = "O'Reilly Radar"`. Venus showed the quotes literally; v2 does not.
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _parse_filters(raw: str | None) -> tuple[re.Pattern[str], ...]:
    if not raw:
        return ()
    return tuple(re.compile(line) for line in raw.split("\n") if line.strip())


def parse(text: str) -> Config:
    # strict=False: duplicate sections are merged (later keys win), matching
    # Python 2 ConfigParser, which Venus used.
    # interpolation=None: date formats contain literal `%`.
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read_string(text)

    planet = parser[PLANET_SECTION]
    link = planet.get("link", "")
    settings = Settings(
        name=planet.get("name", "Planet"),
        link=link,
        feed=planet.get("feed", "") or (urljoin(link, "atom.xml") if link else ""),
        feed_timeout=planet.getint("feed_timeout", 20),
        items_per_page=planet.getint("items_per_page", 60),
        new_feed_items=planet.getint("new_feed_items", 0),
        date_format=planet.get("date_format", "%B %d, %Y %I:%M %p"),
    )

    feeds = tuple(
        Feed(
            url=section,
            name=_unquote(parser.get(section, "name", fallback=section)),
            filters=_parse_filters(parser.get(section, "filter", fallback=None)),
        )
        # Every other section is a feed, even a malformed URL (it then fails
        # to fetch and shows as an error in the sidebar).
        for section in parser.sections()
        if section != PLANET_SECTION
    )
    return Config(settings=settings, feeds=feeds)


def load(path: str | Path) -> Config:
    return parse(Path(path).read_text(encoding="utf-8"))
