#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
sync
echo 'RCP mode bind mounts stay active until reboot and will disappear automatically.'
echo 'post_init.sh was not changed. Remove the OTBR module first if OTBR should stop autostarting.'
