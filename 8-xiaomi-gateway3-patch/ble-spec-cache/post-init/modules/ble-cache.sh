# BLE cache waits for local MQTT/openmiio and retries by itself.
(
    /data/ble-spec-cache/start.sh >>/var/log/ble-spec-cache-clock.log 2>&1 ||
        echo 'POST_INIT_MODULE_FAILED: ble-cache' >>/var/log/ble-spec-cache-clock.log
) &
