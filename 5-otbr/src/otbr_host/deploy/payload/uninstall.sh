#!/bin/sh
set -eu
BASE=/data/otbr
CTL=/data/mi-gw2-post-init/post-initctl.sh
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
[ -x "$CTL" ] || { echo 'Modular post-init manager is missing.' >&2; exit 1; }
rm -f "$BASE/enabled"
"$CTL" remove otbr
sh "$BASE/stop.sh"
sync
echo 'OTBR boot module removed. Other modules and the stock anchor were not changed.'
echo 'OTBR configuration, secrets, state and backups are retained in /data/otbr.'
