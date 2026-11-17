#!/bin/sh
set -eu
BASE=/tmp/rcp-native
[ -s "$BASE/state/paused-pids" ] || { echo 'Run prepare-local.sh first.' >&2; exit 1; }
for PID in $(cat "$BASE/state/paused-pids"); do
    grep -q '^State:.*T' "/proc/$PID/status" || { echo 'Original services are no longer paused.' >&2; exit 1; }
done
/bin/zigbee_isp.sh 0
usleep 100000
/bin/zigbee_reset.sh 1
usleep 100000
/bin/zigbee_reset.sh 0
usleep 100000
/bin/zigbee_isp.sh 1
echo 'Bootloader-entry GPIO sequence sent; no firmware written.'
