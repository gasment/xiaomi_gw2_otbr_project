#!/bin/sh
set -eu
BASE=/tmp/rcp-native
[ -d "$BASE/state" ] || exit 0
/bin/zigbee_isp.sh 1
/bin/zigbee_reset.sh 1
usleep 100000
/bin/zigbee_reset.sh 0
for PID in $(cat "$BASE/state/paused-pids"); do kill -CONT "$PID" 2>/dev/null || true; done
echo 'Original Linux services resumed. This script does not restore radio firmware.'
echo 'Only use with factory Zigbee present; reboot manually for a clean service state.'
