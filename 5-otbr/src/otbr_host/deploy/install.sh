#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
for TOOL in sha256sum cp mv mkdir chmod grep cat tr fuser readlink sed rmdir df touch sleep usleep cut wc rm; do
    command -v "$TOOL" >/dev/null 2>&1 || { echo "Missing tool: $TOOL" >&2; exit 1; }
done
for SCRIPT in /bin/zigbee_isp.sh /bin/zigbee_reset.sh; do
    [ -r "$SCRIPT" ] || { echo "Missing RCP recovery script: $SCRIPT" >&2; exit 1; }
done
sha256sum -c SHA256SUMS
chmod 700 payload/mi-otbr-host
[ ! -e payload/config.yaml ] && [ ! -e payload/secrets.yaml ] || { echo 'Invalid package: runtime config must not be in payload.' >&2; exit 1; }
if [ -f /data/otbr/config.yaml ]; then
    payload/mi-otbr-host /data/otbr/config.yaml --check-config
fi
[ -f /data/scripts/post_init.sh ] || { echo 'Existing boot chain missing' >&2; exit 1; }
if grep -q MI_GATEWAY2_OTBR_HOST_V1 /data/scripts/post_init.sh; then
    [ -f /data/otbr/boot-wrapper.sha256 ] && sha256sum -c /data/otbr/boot-wrapper.sha256 >/dev/null 2>&1 || { echo 'OTBR boot hook changed locally; merge it before upgrading.' >&2; exit 1; }
fi
[ -f /data/rcp-openmiio/start.sh ] && [ -f /data/rcp-mode/apply-mode.sh ] || { echo 'Validated RCP/BLE isolation missing' >&2; exit 1; }
FREE=$(df -k /data | sed -n '2s/  */ /gp' | cut -d ' ' -f 4)
case "$FREE" in ''|*[!0-9]*) echo 'Unable to determine /data free space' >&2; exit 1;; esac
[ "$FREE" -ge 20000 ] || { echo 'Need 20 MiB free on /data for install/backup' >&2; exit 1; }
if [ -f /tmp/mi-otbr-noattach.pid ] && [ -f /tmp/host-noattach-probe/stop.sh ]; then
    sh /tmp/host-noattach-probe/stop.sh
fi
if [ -f /data/otbr/stop.sh ]; then sh /data/otbr/stop.sh; fi
N=0
while [ -n "$(fuser /dev/ttyS1 2>&1 || :)" ] && [ "$N" -lt 15 ]; do sleep 1; N=$((N + 1)); done
[ -z "$(fuser /dev/ttyS1 2>&1 || :)" ] || { echo 'UART still in use; no unrelated process stopped' >&2; exit 1; }
mkdir -p /data/otbr/previous /data/otbr/certs /data/otbr/state
chmod 700 /data/otbr /data/otbr/previous /data/otbr/state
if ! grep -q MI_GATEWAY2_OTBR_HOST_V1 /data/scripts/post_init.sh; then
    cp /data/scripts/post_init.sh /data/otbr/original-post_init.sh
fi
[ -f /data/otbr/original-post_init.sh ] || { echo 'Original boot hook backup missing' >&2; exit 1; }
for F in payload/*; do
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
cp payload/post_init.sh /data/scripts/post_init.sh.new
chmod 755 /data/scripts/post_init.sh.new
mv /data/scripts/post_init.sh.new /data/scripts/post_init.sh
sha256sum /data/scripts/post_init.sh > /data/otbr/boot-wrapper.sha256
touch /data/otbr/enabled
if sh /data/otbr/check.sh > /tmp/mi-otbr-config.log 2>&1; then
    sh /data/otbr/start.sh
    echo 'DEPLOY_INSTALLED: started using existing gateway YAML; BLE/RCP isolation preserved.'
else
    echo 'DEPLOY_INSTALLED_CONFIG_REQUIRED: edit /data/otbr/config.yaml and secrets.yaml, then run sh /data/otbr/restart.sh.'
    cat /tmp/mi-otbr-config.log
fi
echo 'Status: sh /data/otbr/status.sh'
echo 'Rollback: sh /data/otbr/uninstall.sh'
