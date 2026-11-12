"""Keep one version of a post that a feed publishes in several languages.

Versions are recognised by the hreflang links they declare to each other
(see planet.parse). Of each group the English version is kept, else the
earliest published one. Entries that declare no translations are untouched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urldefrag

from planet.model import Entry


@dataclass(frozen=True)
class OnePerPost:
    kept: tuple[Entry, ...]
    dropped: frozenset[str]  # entry ids


def _key(url: str) -> str:
    return urldefrag(url).url


def _is_english(language: str) -> bool:
    return language.lower().replace("_", "-").split("-")[0] == "en"


def one_per_post(entries: Sequence[Entry]) -> OnePerPost:
    by_link = {_key(e.link): e for e in entries if e.link}
    declared = {_key(href): lang for e in entries for href, lang in e.translations}

    # union-find over entry ids
    parent = {e.entry_id: e.entry_id for e in entries}

    def root(entry_id: str) -> str:
        while parent[entry_id] != entry_id:
            parent[entry_id] = parent[parent[entry_id]]
            entry_id = parent[entry_id]
        return entry_id

    for e in entries:
        for href, _ in e.translations:
            other = by_link.get(_key(href))
            if other is not None:
                parent[root(other.entry_id)] = root(e.entry_id)

    groups: dict[str, list[Entry]] = {}
    for e in entries:
        groups.setdefault(root(e.entry_id), []).append(e)

    def language(e: Entry) -> str:
        return e.content_language or (declared.get(_key(e.link)) if e.link else None) or ""

    def preference(e: Entry) -> tuple[bool, float, str]:
        undated = float("inf")
        return (not _is_english(language(e)), e.date or undated, e.link or "")

    dropped = {
        e.entry_id
        for group in groups.values()
        if len(group) > 1
        for e in sorted(group, key=preference)[1:]
    }
    return OnePerPost(
        kept=tuple(e for e in entries if e.entry_id not in dropped),
        dropped=frozenset(dropped),
    )
