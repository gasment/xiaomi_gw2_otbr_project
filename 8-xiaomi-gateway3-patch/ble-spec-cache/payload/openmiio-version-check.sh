#!/bin/sh
set -u
BIN=${1:-}
MIN=${2:-1.2.1}
PROBE=/tmp/openmiio-version-check.$$
LOG=$PROBE.log
cleanup() { rm -f "$PROBE" "$LOG"; }
trap cleanup EXIT HUP INT TERM
[ -n "$BIN" ] && [ -r "$BIN" ] || { echo 'OPENMIIO_VERSION_CHECK_ERROR: binary missing' >&2; exit 2; }
cp "$BIN" "$PROBE" || { echo 'OPENMIIO_VERSION_CHECK_ERROR: copy failed' >&2; exit 2; }
chmod 700 "$PROBE"
"$PROBE" >"$LOG" 2>&1 &
PID=$!
sleep 1
kill "$PID" 2>/dev/null || :
wait "$PID" 2>/dev/null || :
CURRENT=$(sed -n 's/.*openmiio_agent version \([0-9][0-9.]*\).*/\1/p' "$LOG" | tail -n 1)
[ -n "$CURRENT" ] || { echo 'OPENMIIO_VERSION_UNKNOWN' >&2; exit 1; }
awk -v current="$CURRENT" -v minimum="$MIN" '
    BEGIN {
        na=split(current,A,"."); nb=split(minimum,B,".")
        for (i=1;i<=3;i++) {
            a=(i<=na && A[i] != "" ? A[i]+0 : 0)
            b=(i<=nb && B[i] != "" ? B[i]+0 : 0)
            if (a>b) exit 0
            if (a<b) exit 1
        }
        exit 0
    }
' || { echo "OPENMIIO_VERSION_TOO_OLD current=$CURRENT minimum=$MIN" >&2; exit 1; }
echo "OPENMIIO_VERSION_OK current=$CURRENT minimum=$MIN"
exit 0
