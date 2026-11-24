#!/bin/sh
# MI_GW2_BLE_SPEC_CACHE_V1
mkdir -p /var/log
sh /data/ble-spec-cache/start.sh >> /var/log/ble-spec-cache-clock.log 2>&1
exec sh /data/ble-spec-cache/original-post_init.sh
