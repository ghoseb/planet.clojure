"""The persistent cache: feed state + recent entries, in one SQLite file.

This one file is what the Lambda pulls from and pushes to S3 each run.
Entries are kept even after they drop off a feed's live XML (the "planet"
history), up to `keep_per_feed` most recent per feed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

from planet import backoff
from planet.config import Feed
from planet.model import Channel, Entry, FeedMeta, Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
    url            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    title          TEXT,
    link           TEXT,
    subtitle       TEXT,
    feed_id        TEXT,
    updated        REAL,
    rights         TEXT,
    language       TEXT,
    author_name    TEXT,
    author_email   TEXT,
    etag           TEXT,
    last_modified  TEXT,
    last_error     TEXT,      -- NULL when the last fetch succeeded
    last_fetched   REAL,
    failures       INTEGER NOT NULL DEFAULT 0,  -- consecutive failed fetches
    retry_at       REAL       -- don't fetch before this (epoch s); NULL = any time
);
CREATE TABLE IF NOT EXISTS entries (
    feed_url          TEXT NOT NULL REFERENCES feeds(url) ON DELETE CASCADE,
    entry_id          TEXT NOT NULL,
    title             TEXT NOT NULL,
    link              TEXT,
    content           TEXT NOT NULL,
    author_name       TEXT,
    author_email      TEXT,
    title_language    TEXT,
    content_language  TEXT,
    date              REAL NOT NULL,
    first_seen        REAL NOT NULL,
    PRIMARY KEY (feed_url, entry_id)
);
CREATE INDEX IF NOT EXISTS entries_by_date ON entries (date DESC);
"""

_META_COLUMNS = (
    "title",
    "link",
    "subtitle",
    "feed_id",
    "updated",
    "rights",
    "language",
    "author_name",
    "author_email",
)

# Columns added after the first release, for caches created before them:
# (name, declaration). CREATE TABLE IF NOT EXISTS doesn't add columns.
_ADDED_COLUMNS = (
    ("failures", "INTEGER NOT NULL DEFAULT 0"),
    ("retry_at", "REAL"),
)

UNDATED = 0.0  # the date given to entries that carry none: the epoch


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
    for name, declaration in _ADDED_COLUMNS:
        if name not in existing:
            # Only the _ADDED_COLUMNS constants are interpolated.
            conn.execute(f"ALTER TABLE feeds ADD COLUMN {name} {declaration}")


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def open(cls, path: str | Path) -> Store:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        _migrate(conn)
        return cls(conn)

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    # -- subscriptions ----------------------------------------------------

    def sync_subscriptions(self, feeds: Sequence[Feed]) -> None:
        """Make the feeds table match config.ini: add new feeds, update
        names, and drop feeds (and their entries) no longer subscribed."""
        self.conn.executemany(
            "INSERT INTO feeds (url, name) VALUES (?, ?) "
            "ON CONFLICT(url) DO UPDATE SET name = excluded.name",
            [(f.url, f.name) for f in feeds],
        )
        urls = {f.url for f in feeds}
        stale = [
            row["url"]
            for row in self.conn.execute("SELECT url FROM feeds")
            if row["url"] not in urls
        ]
        self.conn.executemany("DELETE FROM feeds WHERE url = ?", [(u,) for u in stale])

    # -- fetch state --------------------------------------------------------

    def validators(self, url: str) -> tuple[str | None, str | None]:
        """(etag, last_modified) from the last successful fetch."""
        row = self.conn.execute(
            "SELECT etag, last_modified FROM feeds WHERE url = ?", (url,)
        ).fetchone()
        return (row["etag"], row["last_modified"]) if row else (None, None)

    def record_success(
        self, url: str, meta: FeedMeta, etag: str | None, last_modified: str | None, now: float
    ) -> None:
        assignments = ", ".join(f"{c} = ?" for c in _META_COLUMNS)
        self.conn.execute(
            # Only the _META_COLUMNS constant is interpolated; values are bound.
            f"UPDATE feeds SET {assignments}, etag = ?, last_modified = ?, "  # noqa: S608
            "last_error = NULL, last_fetched = ?, failures = 0, retry_at = NULL WHERE url = ?",
            (*(getattr(meta, c) for c in _META_COLUMNS), etag, last_modified, now, url),
        )

    def record_not_modified(
        self, url: str, etag: str | None, last_modified: str | None, now: float
    ) -> None:
        self.conn.execute(
            "UPDATE feeds SET etag = ?, last_modified = ?, last_error = NULL, "
            "last_fetched = ?, failures = 0, retry_at = NULL WHERE url = ?",
            (etag, last_modified, now, url),
        )

    def record_error(self, url: str, error: str, now: float) -> float:
        """Record a failed fetch and schedule the next attempt (exponential
        backoff). Returns the time of the next attempt."""
        row = self.conn.execute("SELECT failures FROM feeds WHERE url = ?", (url,)).fetchone()
        failures = (row["failures"] if row else 0) + 1
        retry_at = now + backoff.delay_s(failures)
        self.conn.execute(
            "UPDATE feeds SET last_error = ?, last_fetched = ?, failures = ?, retry_at = ? "
            "WHERE url = ?",
            (error, now, failures, retry_at, url),
        )
        return retry_at

    def last_fetched(self) -> dict[str, float | None]:
        """When each feed was last requested (successfully or not)."""
        rows = self.conn.execute("SELECT url, last_fetched FROM feeds")
        return {r["url"]: r["last_fetched"] for r in rows}

    def backing_off(self, now: float) -> set[str]:
        """Feeds whose next attempt isn't due yet at `now`."""
        rows = self.conn.execute("SELECT url, retry_at FROM feeds WHERE retry_at IS NOT NULL")
        return {r["url"] for r in rows if not backoff.is_due(r["retry_at"], now)}

    # -- entries -------------------------------------------------------------

    def upsert_entries(self, url: str, entries: Iterable[Entry], now: float) -> None:
        """Insert or update entries (`now` is recorded as first_seen).

        Entries without a date keep the date already stored, else get the
        epoch (UNDATED), so an undated post (e.g. old posts of a newly added
        feed) never outranks a dated one. Venus used "now" here instead."""
        for e in entries:
            existing = self.conn.execute(
                "SELECT date FROM entries WHERE feed_url = ? AND entry_id = ?", (url, e.entry_id)
            ).fetchone()
            date = e.date or (existing["date"] if existing else None) or UNDATED
            self.conn.execute(
                """INSERT INTO entries (feed_url, entry_id, title, link, content,
                       author_name, author_email, title_language, content_language,
                       date, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(feed_url, entry_id) DO UPDATE SET
                       title = excluded.title, link = excluded.link,
                       content = excluded.content, author_name = excluded.author_name,
                       author_email = excluded.author_email,
                       title_language = excluded.title_language,
                       content_language = excluded.content_language,
                       date = excluded.date""",
                (
                    url,
                    e.entry_id,
                    e.title,
                    e.link,
                    e.content,
                    e.author_name,
                    e.author_email,
                    e.title_language,
                    e.content_language,
                    date,
                    now,
                ),
            )

    def delete_entries(self, url: str, entry_ids: Iterable[str]) -> None:
        self.conn.executemany(
            "DELETE FROM entries WHERE feed_url = ? AND entry_id = ?",
            [(url, entry_id) for entry_id in entry_ids],
        )

    def prune(self, keep_per_feed: int) -> int:
        """Keep only the `keep_per_feed` most recent entries of each feed."""
        cur = self.conn.execute(
            """DELETE FROM entries WHERE rowid IN (
                   SELECT rowid FROM (
                       SELECT rowid, ROW_NUMBER() OVER (
                           PARTITION BY feed_url ORDER BY date DESC, first_seen DESC
                       ) AS rank FROM entries)
                   WHERE rank > ?)""",
            (keep_per_feed,),
        )
        return cur.rowcount

    # -- reading for render ------------------------------------------------

    def _channel(self, row: sqlite3.Row) -> Channel:
        return Channel(
            url=row["url"],
            name=row["name"],
            meta=FeedMeta(**{c: row[c] for c in _META_COLUMNS}),
            message=row["last_error"],
        )

    def channels(self) -> list[Channel]:
        """All subscriptions, sorted by name (code point order, as Venus)."""
        rows = self.conn.execute("SELECT * FROM feeds").fetchall()
        return sorted((self._channel(r) for r in rows), key=lambda c: c.name)

    def select_items(self, limit: int, per_feed: int = 0) -> list[Item]:
        """Newest first; each entry id once; at most `per_feed` items per
        feed (0 = no cap); at most `limit` items (Venus splice semantics)."""
        channels = {r["url"]: self._channel(r) for r in self.conn.execute("SELECT * FROM feeds")}
        items: list[Item] = []
        seen_ids: set[str] = set()
        per_feed_count: dict[str, int] = {}
        for row in self.conn.execute("SELECT * FROM entries ORDER BY date DESC, first_seen DESC"):
            if len(items) >= limit:
                break
            if row["entry_id"] in seen_ids:
                continue
            count = per_feed_count.get(row["feed_url"], 0)
            if per_feed and count >= per_feed:
                continue
            seen_ids.add(row["entry_id"])
            per_feed_count[row["feed_url"]] = count + 1
            items.append(
                Item(
                    entry_id=row["entry_id"],
                    title=row["title"],
                    link=row["link"],
                    content=row["content"],
                    author_name=row["author_name"],
                    author_email=row["author_email"],
                    date=row["date"],
                    title_language=row["title_language"],
                    content_language=row["content_language"],
                    channel=channels[row["feed_url"]],
                )
            )
        return items
