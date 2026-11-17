#!/bin/sh
set -eu
cd /data/rcp-mode
cmp -s post_init.sh /data/scripts/post_init.sh || { echo 'Boot hook changed; refusing to overwrite it.' >&2; exit 1; }
test -x original-post_init.sh
cp -p original-post_init.sh /data/scripts/post_init.sh.restore
mv -f /data/scripts/post_init.sh.restore /data/scripts/post_init.sh
sync
echo 'Previous boot hook restored. Current mounts stay active until reboot.'
echo 'Restore Zigbee firmware before rebooting with the original Zigbee services.'
