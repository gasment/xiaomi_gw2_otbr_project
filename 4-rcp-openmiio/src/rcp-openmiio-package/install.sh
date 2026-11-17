#!/bin/sh
set -eu
cd "$(dirname "$0")"
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for TOOL in cmp sha256sum cat cp mv chmod chown mkdir rmdir touch tr sleep kill pidof grep rm sync tail timeout agetprop; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing command: $TOOL"
done
[ -x /bin/mbasis_cli ] || fail 'Missing stock mbasis_cli.'
sha256sum -c SHA256SUMS
sha256sum -c payload/openmiio.sha256
cmp -s /data/scripts/post_init.sh /data/rcp-mode/post_init.sh || fail 'Expected RCP boot hook is not active.'
grep -q '^# MI_GATEWAY2_RCP_MODE_V1$' /data/scripts/post_init.sh || fail 'RCP startup marker missing.'
[ ! -e /data/rcp-openmiio ] || fail '/data/rcp-openmiio already exists; inspect it first.'
for SCRIPT in payload/*.sh; do sh -n "$SCRIPT"; done
mkdir /data/rcp-openmiio
cp -p /data/scripts/post_init.sh /data/rcp-openmiio/original-post_init.sh
cp payload/* /data/rcp-openmiio/
chown -R 0:0 /data/rcp-openmiio
chmod 700 /data/rcp-openmiio /data/rcp-openmiio/*.sh
chmod 600 /data/rcp-openmiio/*.sha256
cp /data/rcp-openmiio/post_init.sh /data/scripts/post_init.sh.new
chmod 755 /data/scripts/post_init.sh.new
mv -f /data/scripts/post_init.sh.new /data/scripts/post_init.sh
sync
echo 'Gateway-only BLE/RCP autostart installed. HA files and openmiio binary were not changed.'
echo 'For this boot, run: sh /data/rcp-openmiio/start.sh --now'
