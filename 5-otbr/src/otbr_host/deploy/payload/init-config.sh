#!/bin/sh
set -eu
BASE=/data/otbr
umask 077
for NAME in config.yaml secrets.yaml; do
    if [ "$NAME" = secrets.yaml ] && [ ! -e "$BASE/$NAME" ] && [ ! -L "$BASE/$NAME" ]; then
        if ! grep -q '!secret[[:space:]]' "$BASE/config.yaml"; then
            echo 'Gateway YAML is self-contained; no secrets.yaml created.'
            continue
        fi
    fi
    if [ ! -e "$BASE/$NAME" ] && [ ! -L "$BASE/$NAME" ]; then
        # noclobber also protects an editor creating the file concurrently.
        (set -C; cat "$BASE/$NAME.example" > "$BASE/$NAME")
        chmod 600 "$BASE/$NAME"
        echo "Created gateway-owned $BASE/$NAME; edit it here."
    else
        echo "Preserved gateway-owned $BASE/$NAME."
    fi
done
