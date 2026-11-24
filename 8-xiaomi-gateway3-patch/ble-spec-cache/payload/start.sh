#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
[ ! -f "$BASE/disabled" ] || exit 0
umask 077
cd "$BASE"
sha256sum -c files.sha256 >/dev/null
if [ -r /tmp/gw2-ble-cache-clock.pid ]; then
    PID=$(cat /tmp/gw2-ble-cache-clock.pid)
    case "$PID" in ''|*[!0-9]*) echo 'Invalid BLE clock PID file.' >&2; exit 1;; esac
    if kill -0 "$PID" 2>/dev/null; then
        [ "$(readlink "/proc/$PID/exe")" = "$BASE/ble-cache-clock" ] || { echo 'BLE clock PID belongs to another process.' >&2; exit 1; }
        echo "BLE cache clock already running: $PID"
        exit 0
    fi
fi
"$BASE/ble-cache-clock" </dev/null >> /var/log/ble-spec-cache-clock.log 2>&1 &
sleep 1
PID=$(cat /tmp/gw2-ble-cache-clock.pid 2>/dev/null) || { echo 'BLE cache clock failed to start.' >&2; exit 1; }
kill -0 "$PID" 2>/dev/null || { echo 'BLE cache clock exited.' >&2; exit 1; }
echo "BLE cache clock started: $PID"
