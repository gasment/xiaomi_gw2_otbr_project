#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
sha256sum -c SHA256SUMS
chmod 700 "$BASE" "$BASE/mi-otbr-host"
chmod 600 "$BASE/config.yaml"
if [ -f "$BASE/secrets.yaml" ]; then chmod 600 "$BASE/secrets.yaml"; fi
exec "$BASE/mi-otbr-host" "$BASE/config.yaml" --check-config
