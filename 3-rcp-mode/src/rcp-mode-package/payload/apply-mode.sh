#!/bin/sh
set -eu
cd /data/rcp-mode
sha256sum -c payload.sha256
# Repeated invocation is harmless; never stack bind mounts.
if cmp -s fw_manager.sh /bin/fw_manager.sh && cmp -s app_monitor.sh /bin/app_monitor.sh; then
    echo 'RCP startup isolation is already active.'
    exit 0
fi
sha256sum -c stock.sha256
mount -o bind /data/rcp-mode/app_monitor.sh /bin/app_monitor.sh
if ! mount -o bind /data/rcp-mode/fw_manager.sh /bin/fw_manager.sh; then
    umount /bin/app_monitor.sh
    exit 1
fi
cmp -s fw_manager.sh /bin/fw_manager.sh
cmp -s app_monitor.sh /bin/app_monitor.sh
echo 'RCP startup isolation active: stock Zigbee launch, monitor and coordinator OTA disabled.'
