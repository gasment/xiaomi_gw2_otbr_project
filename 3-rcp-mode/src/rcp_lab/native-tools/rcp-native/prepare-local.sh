#!/bin/sh
set -eu
BASE=/tmp/rcp-native
STATE=$BASE/state
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
[ -x "$BASE/radio-flasher" ] || fail 'Native binary missing.'
(cd "$BASE" && sha256sum -c SHA256SUMS) || fail 'Package integrity check failed.'
[ ! -e "$STATE" ] || fail 'Session already exists. Restore and reboot first.'
[ "$(cat /sys/class/gpio/gpio43/value)" = 1 ] || fail 'Unexpected ISP level.'
[ "$(cat /sys/class/gpio/gpio44/value)" = 0 ] || fail 'Unexpected RESET level.'
SERVICES=
for D in /proc/[0-9]*; do
    [ -d "$D" ] || continue
    PID=${D##*/}
    [ "$PID" = "$$" ] && continue
    CMD=$(tr '\000' ' ' <"$D/cmdline" 2>/dev/null || :)
    case "$CMD" in
        *openmiio_agent*|*app_monitor.sh*)
            case " $SERVICES " in
                *" $PID "*) ;;
                *) SERVICES="$SERVICES $PID" ;;
            esac
            ;;
    esac
done
if [ -z "$SERVICES" ]; then
    echo 'FACTORY_WARNING: original openmiio/app_monitor services are already absent; continuing with UART ownership checks.'
fi
mkdir "$STATE"
: > "$STATE/paused-pids"
cleanup() { for PID in $(cat "$STATE/paused-pids"); do kill -CONT "$PID" 2>/dev/null || true; done; }
trap cleanup 0
trap 'exit 1' 1 2 15
for PID in $SERVICES; do
    case "$PID" in
        ''|*[!0-9]*) continue ;;
    esac
    if grep -q '^State:.*T' "/proc/$PID/status"; then fail 'A service is already stopped.'; fi
    printf '%s\n' "$PID" >> "$STATE/paused-pids"
    kill -STOP "$PID"
done
killall mZ3GatewayHost_MQTT 2>/dev/null || true
sleep 1
if fuser /dev/ttyS1 > "$STATE/serial-users.txt" 2>&1; then cat "$STATE/serial-users.txt"; fail 'UART still in use.'; fi
trap - 0 1 2 15
echo 'Original Zigbee services paused. Native UART access is ready; no network bridge was started.'
