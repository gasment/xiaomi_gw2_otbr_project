#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
DEST=/data/tun
HOOK=/data/scripts/post_init.sh
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
[ -x /bin/fw_manager.sh ] || fail 'Stock Xiaomi service launcher not found.'
for TOOL in uname cat grep sha256sum df awk mkdir cp chmod chown mv cmp insmod mknod ls rm sync date; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing command: $TOOL"
done
agetprop | grep -Eq '\[ro.sys.model\]: \[lumi.gateway.(mcn001|mgl001)\]' || fail 'Unsupported gateway model.'
[ "$(cat /proc/version)" = "$(cat payload/expected-proc-version.txt)" ] || fail 'Kernel build does not match the validated build.'
sha256sum -c SHA256SUMS || fail 'Package integrity check failed.'
for SCRIPT in scripts/start-tun.sh scripts/post_init.sh scripts/uninstall-autostart.sh; do sh -n "$SCRIPT"; done
FREE_KB=$(df -Pk /data | awk 'END {print $4}')
[ "$FREE_KB" -ge 2048 ] || fail 'At least 2048 KiB free space is required on /data.'
if [ -e "$DEST" ] && [ ! -f "$DEST/.mi-gateway2-tun-managed" ]; then
    fail '/data/tun already exists and is not managed by this package.'
fi

MANAGED_HOOK=no
if [ -e "$HOOK" ]; then
    if grep -q 'MI_GATEWAY2_TUN_DEPLOY_V1' "$HOOK"; then
        [ -f "$DEST/managed-post_init.sh" ] && cmp -s "$HOOK" "$DEST/managed-post_init.sh" || fail 'Managed hook has unexpected edits.'
        [ -f "$DEST/original-hook.state" ] || fail 'Original boot hook state is missing.'
        MANAGED_HOOK=yes
    elif grep -q 'MI_GATEWAY2_OPENSSH_DEPLOY_V1' "$HOOK"; then
        :
    elif grep -q '/data/openssh/sbin/sshd' "$HOOK" && grep -q '^exec /bin/fw_manager.sh -r' "$HOOK"; then
        :
    else
        fail 'Unknown custom boot hook: refusing to replace it. Merge manually first.'
    fi
fi

STAMP=$(date +%Y%m%d-%H%M%S)-$$
BACKUP=$DEST/backups/$STAMP
mkdir -p "$BACKUP" /data/scripts
if [ -e "$HOOK" ]; then cp -p "$HOOK" "$BACKUP/post_init.sh"; fi
if [ "$MANAGED_HOOK" = no ]; then
    if [ -e "$HOOK" ]; then
        cp -p "$HOOK" "$DEST/original-post_init.sh"
        printf 'present\n' > "$DEST/original-hook.state"
    else
        rm -f "$DEST/original-post_init.sh"
        printf 'absent\n' > "$DEST/original-hook.state"
    fi
fi
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
put scripts/start-tun.sh "$DEST/start-tun.sh" 755
put scripts/uninstall-autostart.sh "$DEST/uninstall-autostart.sh" 755
put scripts/post_init.sh "$DEST/managed-post_init.sh" 755
: > "$DEST/enabled"
# Test readiness now; enable the boot wrapper only after success.
sh "$DEST/start-tun.sh"
put scripts/post_init.sh "$HOOK" 755
sync
echo "TUN deployment complete. Previous hook backup: $BACKUP"
echo 'Existing SSH, root password and Xiaomi services were not changed or restarted.'
echo 'If TUN was already loaded, the active module was retained; reboot loads the packaged module.'
echo 'Run /data/tun/tun-smoke manually, then reboot manually to verify autostart.'
