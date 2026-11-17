#!/bin/sh
set -eu
. /data/otbr/common.sh
touch "$STOP"
if [ -r "$SUPERVISOR" ]; then
    PID=$(cat "$SUPERVISOR")
    if pid_matches "$PID" supervisor; then
        kill "$PID"
        N=0
        while pid_matches "$PID" supervisor && [ "$N" -lt 20 ]; do sleep 1; N=$((N + 1)); done
        if pid_matches "$PID" supervisor; then echo 'Supervisor still stopping; inspect logs' >&2; exit 1; fi
    fi
fi
if [ -r "$CHILD_PID" ]; then
    PID=$(cat "$CHILD_PID")
    if pid_matches "$PID" host; then
        kill "$PID"
        N=0
        while pid_matches "$PID" host && [ "$N" -lt 12 ]; do sleep 1; N=$((N + 1)); done
        if pid_matches "$PID" host; then kill -9 "$PID"; fi
    fi
fi
sh "$BASE/routing.sh" restore
echo 'OTBR stopped; prior IPv6 routing settings restored. Autostart remains installed.'
