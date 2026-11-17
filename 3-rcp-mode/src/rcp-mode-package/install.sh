#!/bin/sh
set -eu
cd "$(dirname "$0")"
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for tool in sha256sum cmp mount umount cp mv mkdir chmod chown sync grep; do
    command -v "$tool" >/dev/null 2>&1 || fail "Missing tool: $tool"
done
sha256sum -c SHA256SUMS
sha256sum -c payload/stock.sha256
[ ! -e /data/rcp-mode ] || fail '/data/rcp-mode already exists; inspect the previous installation.'
[ -x /data/openssh/start-ssh.sh ] || fail 'Expected working OpenSSH deployment is missing.'
[ -x /data/tun/managed-post_init.sh ] || fail 'Expected TUN boot hook backup is missing.'
cmp -s /data/scripts/post_init.sh /data/tun/managed-post_init.sh || fail 'Current boot hook differs from the known TUN hook.'
for file in payload/*.sh; do sh -n "$file"; done
mkdir /data/rcp-mode
cp -p /data/scripts/post_init.sh /data/rcp-mode/original-post_init.sh
cp payload/* /data/rcp-mode/
chown -R 0:0 /data/rcp-mode
chmod 700 /data/rcp-mode
chmod 700 /data/rcp-mode/*.sh
chmod 600 /data/rcp-mode/*.sha256
(cd /data/rcp-mode && sha256sum -c payload.sha256)
cp /data/rcp-mode/post_init.sh /data/scripts/post_init.sh.new
chmod 755 /data/scripts/post_init.sh.new
mv -f /data/scripts/post_init.sh.new /data/scripts/post_init.sh
sync
echo 'RCP startup isolation installed for NEXT BOOT. No running service, UART or firmware was changed.'
echo 'Keep Home Assistant Xiaomi Gateway 3 integration disabled; reboot manually when ready.'
