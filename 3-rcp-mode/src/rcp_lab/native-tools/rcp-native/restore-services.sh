#!/bin/sh
set -u
BASE=/tmp/rcp-native
STATE=$BASE/state
[ -d "$STATE" ] || exit 0

resume_services() {
    if [ -r "$STATE/paused-pids" ]; then
        for PID in $(cat "$STATE/paused-pids"); do
            case "$PID" in ''|*[!0-9]*) continue;; esac
            kill -CONT "$PID" 2>/dev/null || :
        done
    fi
}
trap resume_services EXIT HUP INT TERM

fail() {
    echo "ERROR: $*" >&2
    resume_services
    exit 1
}

/bin/zigbee_isp.sh 1 || fail 'could not restore ISP level 1'
/bin/zigbee_reset.sh 1 || fail 'could not assert radio reset'
usleep 100000 || :
/bin/zigbee_reset.sh 0 || fail 'could not release radio reset'
resume_services
trap - EXIT HUP INT TERM
rm -rf "$STATE"
sync
echo 'Original Linux services resumed. This script does not restore radio firmware.'
echo 'Session state removed; it is safe to prepare another native UART session.'
