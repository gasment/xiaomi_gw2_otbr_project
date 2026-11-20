#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
sync
echo 'RCP/openmiio runtime supervision remains active until stopped or rebooted.'
echo 'post_init.sh was not changed. Remove the OTBR module first if OTBR should stop autostarting.'
