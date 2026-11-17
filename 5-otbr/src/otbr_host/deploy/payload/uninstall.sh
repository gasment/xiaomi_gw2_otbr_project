#!/bin/sh
set -eu
BASE=/data/otbr
rm -f "$BASE/enabled"
sh "$BASE/stop.sh"
if [ -f "$BASE/boot-wrapper.sha256" ]; then
    if sha256sum -c "$BASE/boot-wrapper.sha256" >/dev/null 2>&1; then
        cp "$BASE/original-post_init.sh" /data/scripts/post_init.sh.new
        chmod 755 /data/scripts/post_init.sh.new
        mv /data/scripts/post_init.sh.new /data/scripts/post_init.sh
        echo 'Original BLE/RCP/TUN/SSH boot chain restored.'
    else
        echo 'Boot hook was modified after installation; retained for manual merge.' >&2
        exit 1
    fi
fi
echo 'OTBR autostart removed; config, secrets, state and backups retained in /data/otbr.'
