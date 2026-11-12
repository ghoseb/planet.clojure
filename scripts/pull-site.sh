#!/bin/sh
# Copy the site published to local S3 (floci) into local/site, then serve it:
#   uv run python -m http.server -d local/site 8000
set -eu
mkdir -p local/site
docker compose run --rm --no-deps -v "$PWD/local/site:/site" \
  --entrypoint aws buckets s3 sync s3://planet-site /site
echo "site in local/site"
