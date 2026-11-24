#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
DEST=/data/tun
HOOK=/data/scripts/post_init.sh
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
[ -x /bin/fw_manager.sh ] || fail 'Stock Xiaomi service launcher not found.'
for TOOL in uname cat grep head tr sha256sum df awk mkdir cp chmod chown mv cmp insmod mknod ls rm rmdir sync date sed touch kill agetprop; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing command: $TOOL"
done
agetprop | grep -Eq '\[ro.sys.model\]: \[lumi.gateway.(mcn001|mgl001)\]' || fail 'Unsupported gateway model.'
sh scripts/check-firmware.sh 1.0.8_0015 || fail 'LUMI_VERSION must be 1.0.8_0015 or newer.'
sha256sum -c SHA256SUMS || fail 'Package integrity check failed.'
for SCRIPT in scripts/check-firmware.sh scripts/start-tun.sh scripts/uninstall-autostart.sh post-init/post-initctl.sh post-init/install-common.sh post-init/migrate-legacy.sh; do sh -n "$SCRIPT"; done
FREE_KB=$(df -Pk /data | awk 'END {print $4}')
[ "$FREE_KB" -ge 2048 ] || fail 'At least 2048 KiB free space is required on /data.'
if [ -e "$DEST" ] && [ ! -f "$DEST/.mi-gateway2-tun-managed" ]; then
    fail '/data/tun already exists and is not managed by this package.'
fi

STAMP=$(date +%Y%m%d-%H%M%S)-$$
BACKUP=$DEST/backups/$STAMP
mkdir -p "$BACKUP" /data/scripts
if [ -e "$HOOK" ]; then cp -p "$HOOK" "$BACKUP/post_init.sh"; fi
: > "$DEST/.mi-gateway2-tun-managed"
put() {
    cp "$1" "$2.new"
    chown 0:0 "$2.new"
    chmod "$3" "$2.new"
    mv -f "$2.new" "$2"
}
put payload/tun.ko "$DEST/tun.ko" 644
put payload/tun-smoke "$DEST/tun-smoke" 755
put payload/expected-proc-version.txt "$DEST/expected-proc-version.txt" 644
put scripts/check-firmware.sh "$DEST/check-firmware.sh" 755
put scripts/start-tun.sh "$DEST/start-tun.sh" 755
put scripts/uninstall-autostart.sh "$DEST/uninstall-autostart.sh" 755
put scripts/post_init.sh "$DEST/managed-post_init.sh" 755
: > "$DEST/enabled"
# Establish the safe shared entry and register only the TUN module.
sh "$BASE/post-init/install-common.sh"
/data/mi-gw2-post-init/post-initctl.sh add tun /data/mi-gw2-post-init/modules/tun.sh
# Test readiness now; a runtime failure does not prevent later boot retries.
sh "$DEST/start-tun.sh"
put VERSION "$DEST/VERSION" 644
sync
echo "TUN deployment complete. post_init backup: $BACKUP"
echo 'Existing SSH, root password and Xiaomi services were not changed or restarted.'
echo 'If TUN was already loaded, the active module was retained; reboot loads the packaged module.'
echo 'Run /data/tun/tun-smoke manually, then reboot manually to verify autostart.'
