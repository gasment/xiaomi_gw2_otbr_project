#!/bin/sh
set -eu
cd "$(dirname "$0")"
BASE=/data/ble-spec-cache
CTL=/data/mi-gw2-post-init/post-initctl.sh
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for T in sha256sum cmp cat cp mv chmod mkdir rmdir rm readlink tr sleep kill pidof sync touch grep awk sed date tail; do
    command -v "$T" >/dev/null 2>&1 || fail "Missing command: $T"
done
sha256sum -c SHA256SUMS
payload/openmiio-version-check.sh /data/openmiio_agent 1.2.1
for SCRIPT in payload/*.sh post-init/*.sh; do sh -n "$SCRIPT"; done
payload/ble-cache-clock --version
[ -n "$(pidof openmiio_agent 2>/dev/null)" ] || fail 'Start openmiio through XiaomiGateway3 before installation.'
if [ -e /data/openmiio_agent.lua ] || [ -L /data/openmiio_agent.lua ]; then
    [ ! -L /data/openmiio_agent.lua ] && cmp -s payload/openmiio_agent.lua /data/openmiio_agent.lua || fail 'An unmanaged openmiio Lua extension already exists; it was preserved.'
fi
[ ! -L "$BASE" ] || fail 'Refusing a symlink installation directory.'
for STAGE in /data/openmiio_agent.lua.new /data/scripts/post_init.sh.new; do
    [ ! -e "$STAGE" ] && [ ! -L "$STAGE" ] || fail "Staging path already exists: $STAGE"
done
if [ -d "$BASE" ]; then
    [ -f "$BASE/installed" ] || fail 'Unmanaged BLE cache directory exists.'
    sh "$BASE/stop.sh"
else
    mkdir "$BASE"
fi
umask 077
for FILE in payload/*; do
    NAME=${FILE##*/}
    cp "$FILE" "$BASE/$NAME.new"
    chmod 600 "$BASE/$NAME.new"
    mv "$BASE/$NAME.new" "$BASE/$NAME"
done
chmod 700 "$BASE" "$BASE/ble-cache-clock" "$BASE"/*.sh
cp payload/openmiio_agent.lua /data/openmiio_agent.lua.new
chmod 600 /data/openmiio_agent.lua.new
mv /data/openmiio_agent.lua.new /data/openmiio_agent.lua
rm -f "$BASE/disabled" /tmp/gw2-ble-spec-cache-status.json
touch "$BASE/installed"
sh post-init/install-common.sh
"$CTL" add ble-cache /data/mi-gw2-post-init/modules/ble-cache.sh
sync
sh "$BASE/start.sh"
sh "$BASE/reload-openmiio.sh"
N=0
READY=no
while [ "$N" -lt 15 ]; do
    for PID in $(pidof openmiio_agent 2>/dev/null); do
        if grep -q '"runtime_pid":'"$PID"'[,}]' /tmp/gw2-ble-spec-cache-status.json 2>/dev/null; then READY=yes; break; fi
    done
    [ "$READY" = no ] || break
    sleep 1; N=$((N + 1))
done
sh "$BASE/status.sh"
[ "$READY" = yes ] || fail 'Current Lua runtime did not report ready; inspect /var/log/openmiio.log. The modular boot entry remains valid.'
echo 'BLE_SPEC_CACHE_INSTALLED: cloud-first policy active. A cold product cache requires WAN learning before offline use.'
