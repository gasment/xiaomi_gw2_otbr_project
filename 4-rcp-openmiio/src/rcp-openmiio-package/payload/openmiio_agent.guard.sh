#!/bin/sh
# This real supervisor name also stays visible to the integration while the
# managed openmiio child restarts. No checksum or binary is impersonated.
set -u
BASE=/data/rcp-openmiio
LOCK=/tmp/rcp-openmiio.lock
READY=/tmp/rcp-openmiio.stock-ready
CHILD=
OWNED=no
LED_WORKER=
# LED_SYNC_FUNCTIONS_BEGIN
# Observe new stock local.status replies rather than trusting a previous boot
# or treating a LAN address as proof that Xiaomi cloud is online.
led_cloud_status() {
    tail -n 1000 "$LED_MESSAGES" 2>/dev/null | grep '"method":"local.status"' | tail -n 1
}
led_sync_tick() {
    LED_STATE=$(agetprop sys.current_state 2>/dev/null) || return 1
    case "$LED_STATE" in
        network_connecting|network_connected) ;;
        '') return 1 ;;
        *) return 0 ;;
    esac
    grep -q 'accept conn app=hardware' "$LED_OPENMIIO_LOG" 2>/dev/null || return 1
    LED_STATUS=$(led_cloud_status)
    [ -n "$LED_STATUS" ] && [ "$LED_STATUS" != "$LED_INITIAL_STATUS" ] || return 1
    case "$LED_STATUS" in *'"params":"cloud_connected"'*) ;; *) return 1 ;; esac
    [ "$LED_TRIES" -lt 3 ] || return 0
    # Recheck the scene immediately before sending; do not dismiss an active
    # identify, pairing, upgrade or alarm scene.
    [ "$(agetprop sys.current_state 2>/dev/null)" = "$LED_STATE" ] || return 1
    LED_TRIES=$((LED_TRIES + 1))
    echo "LED startup sync: cloud online and hardware connected; notifying network_succeeded (attempt $LED_TRIES)."
    LED_REPLY=$(timeout -t 4 -s 9 /bin/mbasis_cli -s basis.network,network_succeeded 2>/dev/null) || {
        echo 'LED startup sync: notification failed or timed out.'
        return 1
    }
    case "$LED_REPLY" in *'"result":["ok"]'*) ;; *)
        echo 'LED startup sync: no verified acknowledgement.'
        return 1 ;;
    esac
    sleep 2
    LED_AFTER=$(agetprop sys.current_state 2>/dev/null) || return 1
    case "$LED_AFTER" in
        system_ready)
            echo 'LED startup sync: verified system_ready.'
            return 0 ;;
        network_connecting|network_connected|'') return 1 ;;
        *) return 0 ;;
    esac
}
led_sync_worker() {
    trap - EXIT
    trap 'exit 0' TERM INT
    LED_MESSAGES=/var/log/messages
    LED_OPENMIIO_LOG=/var/log/openmiio.log
    LED_INITIAL_STATUS=$(led_cloud_status)
    LED_TRIES=0
    LED_POLLS=0
    while [ "$LED_POLLS" -lt 120 ] && kill -0 "$1" 2>/dev/null; do
        LED_CMD=$(tr '\000' ' ' < "/proc/$1/cmdline" 2>/dev/null) || break
        [ "$LED_CMD" = '/data/openmiio_agent miio mqtt cache central ' ] || break
        if led_sync_tick; then return 0; fi
        LED_POLLS=$((LED_POLLS + 1))
        sleep 2
    done
    echo 'LED startup sync: bounded observation ended; no unconditional scene override.'
}
stop_led_sync() {
    if [ -n "$LED_WORKER" ]; then
        kill "$LED_WORKER" 2>/dev/null || :
        wait "$LED_WORKER" 2>/dev/null || :
        LED_WORKER=
    fi
}
# LED_SYNC_FUNCTIONS_END
trap '' HUP
if ! mkdir "$LOCK" 2>/dev/null; then
    echo 'Guard lock exists; refusing a duplicate supervisor.'
    exit 1
fi
printf '%s\n' "$$" > "$LOCK/pid"
cleanup() {
    trap - EXIT TERM INT
    stop_led_sync
    if [ "$OWNED" = yes ] && [ -n "$CHILD" ]; then
        kill "$CHILD" 2>/dev/null || :
        wait "$CHILD" 2>/dev/null || :
    fi
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 0' TERM INT
echo 'Gateway openmiio supervisor started; waiting for stock startup completion.'
while [ ! -f "$READY" ]; do sleep 1; done
echo 'Stock startup complete; BLE/Mesh openmiio supervision enabled.'
while :; do
    CHILD=
    OWNED=no
    # Adopt a clean existing process, so enabling supervision need not interrupt BLE.
    for PID in $(pidof openmiio_agent 2>/dev/null); do
        [ "$PID" != "$$" ] || continue
        CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null) || continue
        case "$CMD" in
            '/data/openmiio_agent miio mqtt cache central ')
                CHILD=$PID
                ;;
            *)
                echo "Stopping openmiio PID $PID with incompatible arguments."
                kill "$PID" 2>/dev/null || :
                COUNT=0
                while kill -0 "$PID" 2>/dev/null && [ "$COUNT" -lt 5 ]; do
                    sleep 1
                    COUNT=$((COUNT + 1))
                done
                # Recheck argv before a stronger signal, avoiding a reused PID.
                NOW=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null) || NOW=
                if [ "$NOW" = "$CMD" ] && [ -n "$NOW" ]; then kill -9 "$PID" 2>/dev/null || :; fi
                ;;
        esac
    done
    if [ -n "$CHILD" ]; then
        echo "Adopted clean openmiio PID $CHILD."
        led_sync_worker "$CHILD" &
        LED_WORKER=$!
        while kill -0 "$CHILD" 2>/dev/null; do
            grep -q '^State:.*Z' "/proc/$CHILD/status" 2>/dev/null && break
            sleep 1
        done
    else
        if ! "$BASE/openmiio-version-check.sh" /data/openmiio_agent 1.2.1 >/dev/null 2>&1; then
            echo 'ERROR: openmiio is older than 1.2.1 or its version cannot be verified; restart withheld.'
            sleep 10
            continue
        fi
        # Always truncate the application log when starting a new child.
        /data/openmiio_agent miio mqtt cache central > /var/log/openmiio.log 2>&1 &
        CHILD=$!
        OWNED=yes
        echo "Started clean openmiio PID $CHILD."
        led_sync_worker "$CHILD" &
        LED_WORKER=$!
        wait "$CHILD" || :
        OWNED=no
    fi
    stop_led_sync
    CHILD=
    echo 'openmiio exited; retrying with BLE/Mesh arguments in two seconds.'
    sleep 2
done
