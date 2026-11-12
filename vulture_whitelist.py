"""Names vulture can't see being used (it reads Python only).

    uv run vulture   # paths and confidence are configured in pyproject.toml
"""

import sqlite3

from planet import handler, main, model

handler.handler  # Lambda entry point, named in the Dockerfile CMD

# RunStats fields are read via dataclasses.asdict() for the run log.
main.RunStats.entries_stored
main.RunStats.total_s

# FeedMeta fields are read by the Jinja templates (atom.xml.j2).
model.FeedMeta.subtitle
model.FeedMeta.updated
model.FeedMeta.rights
model.FeedMeta.language

# Set in Store.open; read by sqlite3 itself.
sqlite3.Connection.row_factory
