#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
CTL=/data/mi-gw2-post-init/post-initctl.sh
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
[ -x "$CTL" ] || { echo 'Modular post-init manager is missing.' >&2; exit 1; }
"$CTL" remove ble-cache
touch "$BASE/disabled"
sh "$BASE/stop.sh"
if [ -e /data/openmiio_agent.lua ]; then
    cmp -s "$BASE/openmiio_agent.lua" /data/openmiio_agent.lua || { echo 'Lua loader differs; refusing to remove it.' >&2; exit 1; }
    rm /data/openmiio_agent.lua
fi
rm -f /tmp/gw2-ble-spec-cache-status.json
sync
sh "$BASE/reload-openmiio.sh"
echo 'BLE Cache boot module removed. Other modules and the stock anchor were not changed.'
echo 'Product cache and executable files are retained for reinstallation.'
