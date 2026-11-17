#!/bin/sh
set -u
. /data/otbr/common.sh
. "$BASE/rcp-recovery.sh"
LOCK=/tmp/mi-otbr-supervisor.lock
if ! mkdir "$LOCK" 2>/dev/null; then
    echo 'Supervisor lock exists; refusing a duplicate.'; exit 0
fi
printf '%s\n' "$$" > "$SUPERVISOR"
CHILD=
cleanup() {
    trap - EXIT INT TERM
    if [ "$RCP_RESET_ASSERTED" -eq 1 ]; then
        rcp_release_reset || echo 'RCP_RECOVERY: ERROR: cleanup could not release RESET'
    fi
    if [ -n "$CHILD" ] && pid_matches "$CHILD" host; then
        kill "$CHILD" 2>/dev/null || :
        N=0
        while pid_matches "$CHILD" host && [ "$N" -lt 12 ]; do sleep 1; N=$((N + 1)); done
        if pid_matches "$CHILD" host; then kill -9 "$CHILD" 2>/dev/null || :; fi
        wait "$CHILD" 2>/dev/null || :
    fi
    sh "$BASE/routing.sh" restore || echo 'ERROR: routing restore failed'
    rm -f "$CHILD_PID" "$SUPERVISOR"
    rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 0' TERM INT
trap '' HUP
rcp_recovery_init || { echo 'Cannot initialize RCP recovery budget'; exit 1; }
echo 'OTBR supervisor waiting for stock BLE/RCP isolation startup.'
while [ -f "$BASE/enabled" ] && [ ! -f "$STOP" ]; do
    if [ ! -f /tmp/rcp-openmiio.stock-ready ]; then sleep 2; continue; fi
    if [ ! -c /dev/net/tun ] && [ -f /data/tun/start-tun.sh ]; then sh /data/tun/start-tun.sh || :; fi
    if [ ! -c /dev/net/tun ]; then echo 'TUN unavailable; retrying'; sleep 5; continue; fi
    BUSY=$(fuser /dev/ttyS1 2>&1 || :)
    if [ -n "$BUSY" ]; then echo "UART occupied by PID(s): $BUSY; retrying without stopping BLE"; sleep 5; continue; fi
    if ! "$BASE/mi-otbr-host" "$BASE/config.yaml" --check-config >> /var/log/mi-otbr-supervisor.log 2>&1; then sleep 10; continue; fi
    if [ -n "$RCP_PENDING_RC" ]; then
        if rcp_recover_pending; then RCP_RESULT=0; else RCP_RESULT=$?; fi
        if [ "$RCP_RESULT" -eq 3 ]; then exit 1; fi
        if [ "$RCP_RESULT" -ne 0 ]; then sleep 2; continue; fi
        [ -f "$STOP" ] && exit 0
    fi
    if ! sh "$BASE/routing.sh" apply; then
        sh "$BASE/routing.sh" restore || :
        echo 'IPv6 routing setup failed'; sleep 5; continue
    fi
    echo 'Starting YAML-configured OTBR Host in --run mode.'
    "$BASE/mi-otbr-host" "$BASE/config.yaml" --run >> /var/log/mi-otbr.log 2>&1 &
    CHILD=$!
    printf '%s\n' "$CHILD" > "$CHILD_PID"
    sleep 1
    while pid_matches "$CHILD" host && [ ! -f "$STOP" ]; do
        sleep 2
        for LOG in /var/log/mi-otbr.log /var/log/mi-otbr-supervisor.log; do
            [ -f "$LOG" ] || continue
            SIZE=$(wc -c < "$LOG")
            if [ "$SIZE" -gt 1048576 ]; then cp "$LOG" "$LOG.1"; : > "$LOG"; fi
        done
    done
    if [ -f "$STOP" ]; then exit 0; fi
    if wait "$CHILD"; then RC=0; else RC=$?; fi
    CHILD=
    rm -f "$CHILD_PID"
    echo "Host exited: $RC"
    if [ ! -f "$STOP" ] && [ -f "$BASE/enabled" ]; then
        rcp_queue_recovery "$RC" || :
    fi
    [ -f "$STOP" ] || sleep 3
done
