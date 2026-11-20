#!/bin/sh
set -eu
CTL=/data/mi-gw2-post-init/post-initctl.sh
[ -x "$CTL" ] || { echo 'Modular post-init manager is missing.' >&2; exit 1; }
"$CTL" remove openssh
sync
echo 'OpenSSH boot module removed. Other modules and the stock anchor were not changed.'
echo 'Existing SSH sessions and listener remain active until stopped or the gateway reboots.'
