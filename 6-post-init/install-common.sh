#!/bin/sh
set -eu
BASE=/data/mi-gw2-post-init
fail() { echo "POST_INIT_COMMON_ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
SRC=$(CDPATH= cd "$(dirname "$0")" && pwd)
[ -f "$SRC/post-initctl.sh" ] || fail 'post-initctl.sh missing from package'
[ -f "$SRC/migrate-legacy.sh" ] || fail 'migrate-legacy.sh missing from package'
mkdir -p "$BASE/modules"
chmod 700 "$BASE" "$BASE/modules"
for NAME in post-initctl.sh migrate-legacy.sh; do
    if [ -e "$BASE/$NAME" ]; then
        [ -f "$BASE/$NAME" ] && [ ! -L "$BASE/$NAME" ] || fail "unsafe installed file: $NAME"
        cmp -s "$SRC/$NAME" "$BASE/$NAME" || fail "installed $NAME differs from this package; upgrade all components to the same post-init API"
    else
        cp "$SRC/$NAME" "$BASE/$NAME.new"
        chmod 700 "$BASE/$NAME.new"
        mv "$BASE/$NAME.new" "$BASE/$NAME"
    fi
done
for FILE in "$SRC"/modules/*.sh; do
    [ -f "$FILE" ] || continue
    NAME=${FILE##*/}
    if [ -e "$BASE/modules/$NAME" ]; then
        [ -f "$BASE/modules/$NAME" ] && [ ! -L "$BASE/modules/$NAME" ] || fail "unsafe installed module: $NAME"
        cmp -s "$FILE" "$BASE/modules/$NAME" || fail "installed module helper differs: $NAME"
    else
        cp "$FILE" "$BASE/modules/$NAME.new"
        chmod 600 "$BASE/modules/$NAME.new"
        mv "$BASE/modules/$NAME.new" "$BASE/modules/$NAME"
    fi
done
if [ -e /data/scripts/post_init.sh ] && ! grep -q '^# MI-GW2-POST-INIT-API: 1$' /data/scripts/post_init.sh; then
    "$BASE/migrate-legacy.sh"
else
    "$BASE/post-initctl.sh" check
fi
sync
echo 'POST_INIT_COMMON_READY'
