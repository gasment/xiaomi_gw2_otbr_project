#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
for TOOL in sha256sum cmp cp mv mkdir chmod grep date cat tr fuser readlink sed rmdir df touch sleep usleep cut wc rm; do
    command -v "$TOOL" >/dev/null 2>&1 || { echo "Missing tool: $TOOL" >&2; exit 1; }
done
for SCRIPT in /bin/zigbee_isp.sh /bin/zigbee_reset.sh; do
    [ -r "$SCRIPT" ] || { echo "Missing RCP recovery script: $SCRIPT" >&2; exit 1; }
done
sha256sum -c SHA256SUMS
chmod 700 payload/mi-otbr-host
[ ! -e payload/config.yaml ] && [ ! -e payload/secrets.yaml ] || { echo 'Invalid package: runtime config must not be in payload.' >&2; exit 1; }
if [ -f /data/otbr/config.yaml ]; then
    if cmp -s examples/config.example /data/otbr/config.yaml &&
       { [ ! -f /data/otbr/secrets.yaml ] || cmp -s examples/secrets.example /data/otbr/secrets.yaml; }; then
        echo OTBR_CONFIG_TEMPLATE_DETECTED
    else
        payload/mi-otbr-host /data/otbr/config.yaml --check-config
    fi
fi
PREREQ_OK=yes
[ -f /data/rcp-openmiio/start.sh ] && [ -f /data/rcp-mode/apply-mode.sh ] || PREREQ_OK=no
FREE=$(df -k /data | sed -n '2s/  */ /gp' | cut -d ' ' -f 4)
case "$FREE" in ''|*[!0-9]*) echo 'Unable to determine /data free space' >&2; exit 1;; esac
[ "$FREE" -ge 20000 ] || { echo 'Need 20 MiB free on /data for install/backup' >&2; exit 1; }
if [ -f /tmp/mi-otbr-noattach.pid ] && [ -f /tmp/host-noattach-probe/stop.sh ]; then
    sh /tmp/host-noattach-probe/stop.sh
fi
if [ -f /data/otbr/stop.sh ]; then sh /data/otbr/stop.sh; fi
START_NOW=yes
N=0
while [ -n "$(fuser /dev/ttyS1 2>&1 || :)" ] && [ "$N" -lt 15 ]; do sleep 1; N=$((N + 1)); done
UART_BUSY=$(fuser /dev/ttyS1 2>&1 || :)
if [ -n "$UART_BUSY" ]; then
    UART_STOCK=
    UART_OTHER=
    for PID in $UART_BUSY; do
        case "$PID" in
            ''|*[!0-9]*) UART_OTHER="$UART_OTHER $PID:invalid"; continue ;;
        esac
        EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || :)
        CMD=$(tr '\000' ' ' <"/proc/$PID/cmdline" 2>/dev/null || :)
        TEXT="$EXE $CMD"
        case "$TEXT" in
            *mZ3GatewayHost_MQTT*|*Z3GatewayHost_MQTT*|*mzigbee_agent*)
                UART_STOCK="$UART_STOCK $PID"
                ;;
            *)
                UART_OTHER="$UART_OTHER $PID:$TEXT"
                ;;
        esac
    done
    if [ -n "$UART_OTHER" ]; then
        echo "UART_BLOCKED_BY_UNMANAGED=$UART_OTHER" >&2
        echo "UART still in use by an unrecognized process; no process was stopped" >&2
        exit 1
    fi
    START_NOW=no
    echo "UART_BUSY_STOCK_DEFERRED=$UART_BUSY"
    echo 'Stock Zigbee keeps the UART until the RCP isolation takes effect on reboot.'
fi
mkdir -p /data/otbr/previous /data/otbr/certs /data/otbr/state
chmod 700 /data/otbr /data/otbr/previous /data/otbr/state
# The rollback snapshot must track the version of the previous Host.
rm -f /data/otbr/previous/VERSION
for F in payload/* VERSION; do
    [ -f "$F" ] || continue
    NAME=${F##*/}
    case "$NAME" in config.yaml|secrets.yaml) echo 'Refusing to overwrite gateway runtime YAML' >&2; exit 1;; esac
    if [ -f "/data/otbr/$NAME" ]; then cp "/data/otbr/$NAME" "/data/otbr/previous/$NAME"; fi
    cp "$F" "/data/otbr/$NAME.new"
    chmod 700 "/data/otbr/$NAME.new"
    mv "/data/otbr/$NAME.new" "/data/otbr/$NAME"
done
cp examples/config.example /data/otbr/config.yaml.example
cp examples/secrets.example /data/otbr/secrets.yaml.example
sh /data/otbr/init-config.sh
chmod 600 /data/otbr/config.yaml
if [ -f /data/otbr/secrets.yaml ]; then chmod 600 /data/otbr/secrets.yaml; fi
if [ ! -e /data/otbr/certs/ca-certificates.crt ]; then cp certs/ca-certificates.crt /data/otbr/certs/ca-certificates.crt; fi
chmod 644 /data/otbr/certs/ca-certificates.crt
touch /data/otbr/enabled
sh post-init/install-common.sh
/data/mi-gw2-post-init/post-initctl.sh add otbr /data/mi-gw2-post-init/modules/otbr.sh
CONFIG_OK=no
if sh /data/otbr/check.sh > /tmp/mi-otbr-config.log 2>&1; then CONFIG_OK=yes; fi
if [ "$START_NOW" = no ]; then
    echo 'DEPLOY_INSTALLED_DEFERRED: OTBR module registered; reboot required to release the UART and start Host.'
    [ "$CONFIG_OK" = yes ] || cat /tmp/mi-otbr-config.log 2>/dev/null || :
elif [ "$CONFIG_OK" = yes ] && [ "$PREREQ_OK" = yes ]; then
    /data/otbr/boot-manager.sh --now >> /var/log/otbr-boot-manager.log 2>&1 &
    echo 'DEPLOY_INSTALLED: OTBR module registered and boot manager started.'
else
    echo 'DEPLOY_INSTALLED_DEGRADED: OTBR module registered but prerequisites or config are incomplete.'
    cat /tmp/mi-otbr-config.log 2>/dev/null || :
fi
echo 'Status: sh /data/otbr/status.sh'
echo 'Rollback: sh /data/otbr/uninstall.sh'
