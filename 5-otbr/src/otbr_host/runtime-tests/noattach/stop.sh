#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
PIDFILE=/tmp/mi-otbr-noattach.pid
[ -r "$PIDFILE" ] || { echo 'No test PID file found.'; exit 0; }
PID=$(cat "$PIDFILE")
case "$PID" in ''|*[!0-9]*) echo 'Invalid PID; inspect it manually.' >&2; exit 1;; esac
if ! kill -0 "$PID" 2>/dev/null; then echo 'Test process has already exited.'; exit 0; fi
CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline")
case "$CMD" in
    "$BASE/mi-otbr-host $BASE/config.yaml --no-attach ") ;;
    *) echo 'PID does not match this exact test command; refusing to signal it.' >&2; exit 1;;
esac
kill "$PID"
echo 'SIGTERM sent to this no-attach test only. Its foreground launcher will clean up.'
