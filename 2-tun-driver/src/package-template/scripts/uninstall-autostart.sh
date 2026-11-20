#!/bin/sh
set -eu
BASE=/data/tun
CTL=/data/mi-gw2-post-init/post-initctl.sh
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root.'
[ -x "$CTL" ] || fail 'Modular post-init manager is missing.'
"$CTL" remove tun
rm -f "$BASE/enabled"
sync
echo 'TUN boot module removed. Other modules and the stock anchor were not changed.'
echo 'TUN files and the currently loaded driver are retained. Reboot to disable autostart.'
