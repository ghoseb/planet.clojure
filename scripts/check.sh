#!/bin/sh
# Every static check plus the tests. Exits non-zero on the first failure.
set -eu
uv run ruff format --check
uv run ruff check
uv run basedpyright
uv run vulture
uv run pytest -q
