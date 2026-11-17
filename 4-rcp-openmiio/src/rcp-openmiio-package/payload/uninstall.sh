#!/bin/sh
set -eu
cd /data/rcp-openmiio
cmp -s post_init.sh /data/scripts/post_init.sh || { echo 'Boot hook changed; refusing to overwrite it.' >&2; exit 1; }
cp -p original-post_init.sh /data/scripts/post_init.sh.restore
mv -f /data/scripts/post_init.sh.restore /data/scripts/post_init.sh
sync
echo 'Previous RCP boot hook restored. Runtime supervisor and openmiio remain running until reboot.'
echo 'Before reboot, disable this gateway entry unless another BLE-only startup method is ready.'
