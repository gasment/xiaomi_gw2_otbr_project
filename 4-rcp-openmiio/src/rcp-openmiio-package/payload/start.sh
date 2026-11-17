#!/bin/sh
set -eu
BASE=/data/rcp-openmiio
LOCK=/tmp/rcp-openmiio.lock
if [ "${1:-}" = --now ]; then touch /tmp/rcp-openmiio.stock-ready; fi
if [ -r "$LOCK/pid" ]; then
    PID=$(cat "$LOCK/pid")
    case "$PID" in ''|*[!0-9]*) echo 'Invalid supervisor PID; inspect the lock.' >&2; exit 1;; esac
    if kill -0 "$PID" 2>/dev/null; then
        CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline")
        case "$CMD" in *'/data/rcp-openmiio/openmiio_agent.guard.sh'*) echo "Supervisor already running: $PID"; exit 0;; esac
        echo 'Lock PID belongs to another process; inspect it.' >&2
        exit 1
    fi
    rm -f "$LOCK/pid"
    rmdir "$LOCK"
fi
if [ -d "$LOCK" ]; then echo 'Incomplete lock directory; inspect it before starting.' >&2; exit 1; fi
mkdir -p /var/log
cd "$BASE"
sha256sum -c scripts.sha256
sh "$BASE/openmiio_agent.guard.sh" </dev/null >> /var/log/rcp-openmiio.log 2>&1 &
sleep 1
[ -r "$LOCK/pid" ] || { echo 'Supervisor did not start; inspect /var/log/rcp-openmiio.log.' >&2; exit 1; }
echo "Supervisor started: $(cat "$LOCK/pid")"
