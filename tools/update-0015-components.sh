#!/bin/sh
# Update an existing managed installation without replacing its boot-hook chain.
set -eu
[ "$#" -eq 3 ] || { echo 'Usage: sh update-0015-components.sh TUN.tar.gz RCP-MODE.tar.gz OTBR.tar.gz' >&2; exit 1; }
[ "$(id -u)" = 0 ] || exit 1
[ "$(agetprop ro.sys.mi_fw_ver)_$(agetprop ro.sys.mi_build_num)" = 1.0.8_0015 ] || { echo 'Stock 1.0.8_0015 required' >&2; exit 1; }
WORK=/tmp/mi-gw2-update-0015-$$
mkdir -m 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$1" -C "$WORK"
tar -xzf "$2" -C "$WORK"
tar -xzf "$3" -C "$WORK"
TUN=$WORK/mi_gateway_2_tun_deploy
MODE=$WORK/rcp-mode
HOST=$WORK/otbr-deploy
for package in "$TUN" "$MODE" "$HOST"; do (cd "$package" && sha256sum -c SHA256SUMS); done
[ "$(cat "$TUN/VERSION")" = "$(cat "$MODE/VERSION")" ]
[ "$(cat "$TUN/VERSION")" = "$(cat "$HOST/VERSION")" ]
[ "$(cat /proc/version)" = "$(cat "$TUN/payload/expected-proc-version.txt")" ] || { echo 'Kernel baseline mismatch' >&2; exit 1; }
if ! cmp -s "$MODE/payload/fw_manager.sh" /bin/fw_manager.sh || ! cmp -s "$MODE/payload/app_monitor.sh" /bin/app_monitor.sh; then
    (cd "$MODE" && sha256sum -c payload/stock.sha256)
fi
[ -x /data/otbr/stop.sh ] && [ -f /data/otbr/config.yaml ]
[ -f /data/rcp-mode/original-post_init.sh ] && [ -f /data/tun/.mi-gateway2-tun-managed ]
sh /data/otbr/stop.sh
put() { cp "$1" "$2.new"; chmod "$3" "$2.new"; mv -f "$2.new" "$2"; }
# No original-post_init.sh is replaced: these are active links in the boot chain.
for file in "$MODE"/payload/*; do put "$file" "/data/rcp-mode/${file##*/}" 700; done
sh /data/rcp-mode/apply-mode.sh
killall app_monitor.sh 2>/dev/null || true
nohup /bin/app_monitor.sh </dev/null >/var/log/app-monitor-restart.log 2>&1 &
killall mZ3GatewayHost_MQTT mzigbee_agent Z3GatewayHost_MQTT 2>/dev/null || true
if grep -q '^tun ' /proc/modules; then rmmod tun; fi
put "$TUN/payload/tun.ko" /data/tun/tun.ko 644
put "$TUN/payload/tun-smoke" /data/tun/tun-smoke 755
put "$TUN/payload/expected-proc-version.txt" /data/tun/expected-proc-version.txt 644
put "$TUN/scripts/start-tun.sh" /data/tun/start-tun.sh 755
sh /data/tun/start-tun.sh
/data/tun/tun-smoke
for file in "$HOST"/payload/*; do put "$file" "/data/otbr/${file##*/}" 700; done
mkdir -p /data/otbr/certs
put "$HOST/certs/ca-certificates.crt" /data/otbr/certs/ca-certificates.crt 644
sync
sh /data/otbr/start.sh
echo 'BASELINE_0015_COMPONENTS_UPDATED: configuration, state and original boot hooks retained; verify status and reboot autostart.'
