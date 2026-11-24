#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
[ -r /tmp/gw2-ble-cache-clock.pid ] || exit 0
PID=$(cat /tmp/gw2-ble-cache-clock.pid)
case "$PID" in ''|*[!0-9]*) echo 'Invalid BLE clock PID file.' >&2; exit 1;; esac
if kill -0 "$PID" 2>/dev/null; then
    [ "$(readlink "/proc/$PID/exe")" = "$BASE/ble-cache-clock" ] || { echo 'Refusing to signal an unrelated process.' >&2; exit 1; }
    kill "$PID"
    N=0
    while kill -0 "$PID" 2>/dev/null && [ "$N" -lt 6 ]; do sleep 1; N=$((N + 1)); done
    if kill -0 "$PID" 2>/dev/null; then echo 'BLE clock did not stop; no force kill was sent.' >&2; exit 1; fi
fi
