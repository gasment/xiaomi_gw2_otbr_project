#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
cmp -s "$BASE/post_init.sh" /data/scripts/post_init.sh || { echo 'Boot hook differs; refusing to overwrite it.' >&2; exit 1; }
cmp -s "$BASE/openmiio_agent.lua" /data/openmiio_agent.lua || { echo 'Lua loader differs; refusing to remove it.' >&2; exit 1; }
[ -f "$BASE/original-post_init.sh" ] || exit 1
touch "$BASE/disabled"
sh "$BASE/stop.sh"
cp "$BASE/original-post_init.sh" /data/scripts/post_init.sh.new
chmod 755 /data/scripts/post_init.sh.new
mv /data/scripts/post_init.sh.new /data/scripts/post_init.sh
if [ -f "$BASE/original-hook-absent" ]; then rm /data/scripts/post_init.sh; fi
rm /data/openmiio_agent.lua
rm -f /tmp/gw2-ble-spec-cache-status.json
sync
sh "$BASE/reload-openmiio.sh"
echo 'BLE Spec patch disabled; previous boot hook restored. Product cache retained for inspection/reinstall.'
