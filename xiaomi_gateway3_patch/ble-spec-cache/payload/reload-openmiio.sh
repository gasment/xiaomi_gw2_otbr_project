#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
cd "$BASE"
sha256sum -c openmiio.sha256 >/dev/null
PID=
for PID in $(pidof openmiio_agent 2>/dev/null); do
    [ "$(readlink "/proc/$PID/exe")" = /data/openmiio_agent ] || exit 1
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
kill "$FOUND"
N=0
while kill -0 "$FOUND" 2>/dev/null; do
    [ "$N" -lt 8 ] || { echo 'openmiio did not stop; no force kill sent.' >&2; exit 1; }
    sleep 1; N=$((N + 1))
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
