#!/bin/sh
set -eu
BASE=/data/tun
fail() { echo "TUN ERROR: $*" >&2; exit 1; }
[ -f "$BASE/enabled" ] || { echo 'TUN autostart is disabled.'; exit 0; }
sh "$BASE/check-firmware.sh" 1.0.8_0015 >/dev/null || fail 'LUMI_VERSION is older than 1.0.8_0015; module was not loaded.'
[ "$(uname -r)" = 4.9.84 ] || fail 'Unsupported kernel release.'
if ! grep -q '^tun ' /proc/modules; then
    insmod "$BASE/tun.ko"
fi
[ -r /sys/class/misc/tun/dev ] || fail 'Driver did not register a TUN device.'
[ "$(cat /sys/class/misc/tun/dev)" = 10:200 ] || fail 'Unexpected TUN device number.'
mkdir -p /dev/net
if [ ! -e /dev/net/tun ]; then
    mknod /dev/net/tun c 10 200
fi
[ -c /dev/net/tun ] || fail '/dev/net/tun is not a character device.'
ls -ln /dev/net/tun | awk '$5 == "10," && $6 == "200" {ok=1} END {exit !ok}' || fail 'Existing node is not device 10:200.'
chown 0:0 /dev/net/tun
chmod 600 /dev/net/tun
echo 'TUN ready: driver loaded and /dev/net/tun is 10:200.'
