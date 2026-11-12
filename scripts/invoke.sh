#!/bin/sh
# Invoke the locally running Lambda container once (see compose.yaml).
set -eu
curl -sS --max-time 960 -X POST \
  http://localhost:9000/2015-03-31/functions/function/invocations -d '{}'
echo
