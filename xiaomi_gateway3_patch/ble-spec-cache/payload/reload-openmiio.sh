#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
cd "$BASE"
"$BASE/openmiio-version-check.sh" /data/openmiio_agent 1.2.1 >/dev/null
PID=
for PID in $(pidof openmiio_agent 2>/dev/null); do
    EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || :)
    case "$EXE" in
        /data/openmiio_agent|'/data/openmiio_agent (deleted)') ;;
        *)
            echo "openmiio PID $PID executable mismatch: ${EXE:-unknown}" >&2
            exit 1
            ;;
    esac
    [ -z "${FOUND:-}" ] || { echo 'Multiple openmiio processes; restart withheld.' >&2; exit 1; }
    FOUND=$PID
done
[ -n "${FOUND:-}" ] || { echo 'No running openmiio; start it through the existing integration first.' >&2; exit 1; }
ARGS=$(tr '\000' ' ' < "/proc/$FOUND/cmdline")
if tr '\000' '\n' < "/proc/$FOUND/cmdline" | grep -q '[[:space:]]'; then
    echo 'Arguments contain whitespace; restart openmiio manually.' >&2; exit 1
fi
# Accept only simple argv tokens; never eval a process command line.
case "$ARGS" in ''|*[!a-zA-Z0-9_./:=,@+\ -]*) echo 'Unsupported argument characters; restart openmiio manually.' >&2; exit 1;; esac
set -f
set -- $ARGS
[ "$1" = /data/openmiio_agent ] || exit 1
pid_alive() {
    PID_TO_CHECK=$1
    [ -d "/proc/$PID_TO_CHECK" ] || return 1
    STATE=$(awk '/^State:/{print $2; exit}' "/proc/$PID_TO_CHECK/status" 2>/dev/null || :)
    case "$STATE" in
        Z*) return 1 ;;
    esac
    kill -0 "$PID_TO_CHECK" 2>/dev/null
}
kill "$FOUND"
N=0
while pid_alive "$FOUND"; do
    [ "$N" -lt 8 ] && { sleep 1; N=$((N + 1)); continue; }
    echo "openmiio did not stop after SIGTERM; escalating to SIGKILL: $FOUND"
    kill -9 "$FOUND" 2>/dev/null || :
    N=0
    while pid_alive "$FOUND" && [ "$N" -lt 4 ]; do
        sleep 1; N=$((N + 1))
    done
    pid_alive "$FOUND" && { echo "openmiio still exists after SIGKILL: $FOUND; reboot required." >&2; exit 1; }
    break
done
# Give an existing HA/gateway supervisor the first opportunity to restart it.
N=0
while [ "$N" -lt 8 ]; do
    if pidof openmiio_agent >/dev/null 2>&1; then
        echo 'openmiio restarted by existing service management.'; exit 0
    fi
    sleep 1; N=$((N + 1))
done
"$@" </dev/null >> /var/log/openmiio.log 2>&1 &
echo "Restarted standalone openmiio with preserved arguments: $!"
