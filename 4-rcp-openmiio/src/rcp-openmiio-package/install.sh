#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
DEST=/data/rcp-openmiio
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
for TOOL in cmp sha256sum cat cp mv chmod chown mkdir rmdir touch tr sleep kill pidof grep rm sync tail timeout agetprop; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing command: $TOOL"
done
[ -x /bin/mbasis_cli ] || fail 'Missing stock mbasis_cli.'
sha256sum -c SHA256SUMS
payload/openmiio-version-check.sh /data/openmiio_agent 1.2.1
if [ -e "$DEST" ] && [ ! -f "$DEST/install.sh" ] && [ ! -f "$DEST/start.sh" ]; then fail 'Unmanaged /data/rcp-openmiio exists.'; fi
mkdir -p "$DEST"
for FILE in payload/*; do
    NAME=${FILE##*/}
    cp "$FILE" "$DEST/$NAME.new"
    chmod 600 "$DEST/$NAME.new"
    mv -f "$DEST/$NAME.new" "$DEST/$NAME"
done
chown -R 0:0 "$DEST"
chmod 700 "$DEST" "$DEST"/*.sh
chmod 600 "$DEST"/*.sha256
sync
echo 'RCP/openmiio helper installed for the OTBR boot manager. post_init.sh was not changed.'
echo 'For this boot, run: sh /data/rcp-openmiio/start.sh --now'
