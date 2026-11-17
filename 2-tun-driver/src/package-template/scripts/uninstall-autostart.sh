#!/bin/sh
set -eu
BASE=/data/tun
HOOK=/data/scripts/post_init.sh
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root.'
[ -f "$BASE/original-hook.state" ] || fail 'Original hook state not found.'
[ -f "$HOOK" ] && cmp -s "$HOOK" "$BASE/managed-post_init.sh" || fail 'Current boot hook changed; inspect it before restoring.'
STATE=$(cat "$BASE/original-hook.state")
case "$STATE" in
    present)
        [ -f "$BASE/original-post_init.sh" ] || fail 'Original hook backup is missing.'
        cp -p "$BASE/original-post_init.sh" "$HOOK.restore"
        mv -f "$HOOK.restore" "$HOOK"
        ;;
    absent) rm -f "$HOOK" ;;
    *) fail 'Unknown original hook state.' ;;
esac
rm -f "$BASE/enabled"
sync
echo 'Previous startup hook restored. TUN files and the currently loaded module are retained.'
echo 'No SSH session or Xiaomi service was stopped. Reboot manually if desired.'
