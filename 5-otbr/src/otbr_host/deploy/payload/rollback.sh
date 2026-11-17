#!/bin/sh
set -eu
BASE=/data/otbr
[ -f "$BASE/previous/mi-otbr-host" ] || { echo 'No previous Host release; use uninstall.sh for first-install rollback.' >&2; exit 1; }
sh "$BASE/stop.sh"
for F in "$BASE"/previous/*; do
    [ -f "$F" ] || continue
    NAME=${F##*/}
    case "$NAME" in config.yaml|secrets.yaml|ca-certificates.crt) continue;; esac
    cp "$F" "$BASE/$NAME.new"
    chmod 700 "$BASE/$NAME.new"
    mv "$BASE/$NAME.new" "$BASE/$NAME"
done
chmod 600 "$BASE/config.yaml"
if [ -f "$BASE/secrets.yaml" ]; then chmod 600 "$BASE/secrets.yaml"; fi
exec sh "$BASE/start.sh"
