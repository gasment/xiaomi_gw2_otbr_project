#!/bin/sh
set -eu
. /data/otbr/common.sh
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
if [ -r "$SUPERVISOR" ] && pid_matches "$(cat "$SUPERVISOR")" supervisor; then
    echo "OTBR supervisor already running: $(cat "$SUPERVISOR")"; exit 0
fi
mkdir -p /var/log
if [ -d /tmp/mi-otbr-supervisor.lock ]; then
    if [ -r "$SUPERVISOR" ]; then
        rm -f "$SUPERVISOR"
        rmdir /tmp/mi-otbr-supervisor.lock || { echo 'Unexpected supervisor lock contents' >&2; exit 1; }
    else
        echo 'Supervisor startup/cleanup already in progress; retry shortly.'; exit 0
    fi
fi
"$BASE/mi-otbr-host" "$BASE/config.yaml" --check-config > /tmp/mi-otbr-config.log 2>&1 || { cat /tmp/mi-otbr-config.log; exit 1; }
touch "$BASE/enabled"
rm -f "$STOP"
(trap '' HUP; exec sh "$BASE/supervisor.sh") >> /var/log/mi-otbr-supervisor.log 2>&1 < /dev/null &
echo "OTBR supervisor launched: $!; Host will read /data/otbr/config.yaml and enable Thread."
