#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
DEST=/data/rcp-mode
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for TOOL in sha256sum cmp mount umount cp mv mkdir chmod chown sync grep awk; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing tool: $TOOL"
done
sha256sum -c SHA256SUMS
if [ -e "$DEST" ] && [ ! -f "$DEST/install.sh" ]; then fail 'Unmanaged /data/rcp-mode exists.'; fi
mkdir -p "$DEST"
BACKUP=$DEST/backups/$(date +%Y%m%d-%H%M%S)-$$
mkdir -p "$BACKUP"
cp -p /bin/fw_manager.sh "$BACKUP/fw_manager.sh"
cp -p /bin/app_monitor.sh "$BACKUP/app_monitor.sh"
for FILE in payload/*; do
    NAME=${FILE##*/}
    cp "$FILE" "$DEST/$NAME.new"
    chmod 600 "$DEST/$NAME.new"
    mv -f "$DEST/$NAME.new" "$DEST/$NAME"
done
sh scripts/patch-launchers.sh /bin/fw_manager.sh "$DEST/fw_manager.sh" /bin/app_monitor.sh "$DEST/app_monitor.sh"
chown -R 0:0 "$DEST"
chmod 700 "$DEST" "$DEST"/*.sh "$DEST"/fw_manager.sh "$DEST"/app_monitor.sh
chmod 600 "$DEST"/*.sha256
(cd "$DEST" && sha256sum app_monitor.sh apply-mode.sh fw_manager.sh post_init.sh stock.sha256 uninstall.sh > payload.sha256.new && mv -f payload.sha256.new payload.sha256)
(cd "$DEST" && sha256sum -c payload.sha256)
sync
echo 'RCP mode helper installed for the OTBR boot manager. post_init.sh was not changed.'
echo 'The OTBR module applies this helper before stock startup on the next boot.'
echo "Original launchers backed up to $BACKUP"
