#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
PIDFILE=/tmp/mi-otbr-noattach.pid
LOG=/tmp/mi-otbr-noattach.log
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for TOOL in sha256sum fuser grep cat mkdir tail chmod rm sleep; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing tool: $TOOL"
done
sha256sum -c SHA256SUMS
[ -c /dev/net/tun ] || fail 'Persistent TUN deployment is not ready.'
[ -c /dev/ttyS1 ] || fail 'UART device missing.'
[ ! -e /sys/class/net/mgotbr0 ] || fail 'mgotbr0 already exists; inspect the previous test before starting.'
if [ -r "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    case "$PID" in ''|*[!0-9]*) fail 'Malformed old test PID file.';; esac
    if kill -0 "$PID" 2>/dev/null; then fail 'A process still owns the previous test PID; inspect it.'; fi
    rm -f "$PIDFILE"
fi
BUSY=$(fuser /dev/ttyS1 2>&1 || :)
[ -z "$BUSY" ] || fail "UART unavailable: $BUSY"
chmod 700 "$BASE" "$BASE/mi-otbr-host"
chmod 600 "$BASE/secrets.yaml"
mkdir -p /tmp/mi-otbr-noattach/state
CHILD=
TAIL=
cleanup() {
    trap - EXIT INT TERM HUP
    if [ -n "$CHILD" ]; then kill "$CHILD" 2>/dev/null || :; wait "$CHILD" 2>/dev/null || :; fi
    if [ -n "$TAIL" ]; then kill "$TAIL" 2>/dev/null || :; wait "$TAIL" 2>/dev/null || :; fi
    rm -f "$PIDFILE"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
: > "$LOG"
"$BASE/mi-otbr-host" "$BASE/config.yaml" --no-attach > "$LOG" 2>&1 &
CHILD=$!
printf '%s\n' "$CHILD" > "$PIDFILE"
echo "No-attach test PID=$CHILD. Native API port=6053, TUN=mgotbr0."
echo 'Web port=18080, Basic user=test; password is in this test bundle secrets.yaml.'
echo 'Waiting in foreground. Run sh test-host-noattach.sh in WSL after CORE_RUNTIME_READY appears.'
echo "Ctrl+C stops this test. Log: $LOG"
tail -n 80 -f "$LOG" &
TAIL=$!
if wait "$CHILD"; then RC=0; else RC=$?; fi
CHILD=
echo "Host exited: $RC"
if [ "$RC" -ne 0 ]; then
    echo "Full failure log: $LOG"
    cat "$LOG"
fi
exit "$RC"
