#!/bin/sh
set -eu
cd "$(dirname "$0")"
BASE=/data/ble-spec-cache
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for T in sha256sum cmp cat cp mv chmod mkdir rm readlink tr sleep kill pidof sync touch grep; do
    command -v "$T" >/dev/null 2>&1 || fail "Missing command: $T"
done
sha256sum -c SHA256SUMS
sha256sum -c payload/openmiio.sha256
for SCRIPT in payload/*.sh; do sh -n "$SCRIPT"; done
payload/ble-cache-clock --version
mkdir -p /data/scripts /var/log
[ -n "$(pidof openmiio_agent 2>/dev/null)" ] || fail 'Start openmiio through XiaomiGateway3 before installation.'
[ ! -L /data/scripts/post_init.sh ] || fail 'Symlink boot hook requires manual integration.'
if [ -e /data/openmiio_agent.lua ] || [ -L /data/openmiio_agent.lua ]; then
    [ ! -L /data/openmiio_agent.lua ] && cmp -s payload/openmiio_agent.lua /data/openmiio_agent.lua || fail 'An unmanaged openmiio Lua extension already exists; it was preserved.'
fi
[ ! -L "$BASE" ] || fail 'Refusing a symlink installation directory.'
for STAGE in /data/openmiio_agent.lua.new /data/scripts/post_init.sh.new; do
    [ ! -e "$STAGE" ] && [ ! -L "$STAGE" ] || fail "Staging path already exists: $STAGE"
done
if [ -d "$BASE" ]; then
    [ -f "$BASE/installed" ] && [ -f "$BASE/original-post_init.sh" ] || fail 'Unmanaged BLE cache directory exists.'
    if ! cmp -s "$BASE/post_init.sh" /data/scripts/post_init.sh; then
        cmp -s "$BASE/original-post_init.sh" /data/scripts/post_init.sh || fail 'Boot hook changed since patch installation.'
    fi
else
    [ ! -e /data/scripts/post_init.sh ] || [ -f /data/scripts/post_init.sh ] || fail 'Invalid boot hook.'
fi
umask 077
if [ -d "$BASE" ]; then sh "$BASE/stop.sh"; else
    mkdir "$BASE"
    if [ -f /data/scripts/post_init.sh ]; then
        cp /data/scripts/post_init.sh "$BASE/original-post_init.sh"
    else
        printf '#!/bin/sh\nexit 0\n' > "$BASE/original-post_init.sh"
        touch "$BASE/original-hook-absent"
    fi
fi
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
cp "$BASE/post_init.sh" /data/scripts/post_init.sh.new
chmod 755 /data/scripts/post_init.sh.new
mv /data/scripts/post_init.sh.new /data/scripts/post_init.sh
rm -f "$BASE/disabled" /tmp/gw2-ble-spec-cache-status.json
touch "$BASE/installed"
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
[ "$READY" = yes ] || fail 'Current Lua runtime did not report ready; inspect /var/log/openmiio.log. Uninstall script is available in the installation directory.'
echo 'BLE_SPEC_CACHE_INSTALLED: cloud-first policy active. A cold product cache requires WAN learning before offline use.'
