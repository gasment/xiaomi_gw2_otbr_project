#!/bin/sh
# Explicit one-time migration from the known legacy nested hook chain.
set -eu
BASE=/data/mi-gw2-post-init
HOOK=/data/scripts/post_init.sh
CTL=$BASE/post-initctl.sh
MODULES=$BASE/modules
fail() { echo "POST_INIT_MIGRATION_ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
[ -x "$CTL" ] || fail 'post-initctl.sh is not installed'
[ -d "$MODULES" ] || fail 'module bodies are not installed'

if [ -e "$HOOK" ] && grep -q '^# MI-GW2-POST-INIT-API: 1$' "$HOOK"; then
    "$CTL" check
    echo 'POST_INIT_ALREADY_MODULAR'
    exit 0
fi

CUR=$HOOK
SEEN=
COMPONENTS=
BASE_MODE=stock
BASE_FILE=
COUNT=0
while :; do
    COUNT=$((COUNT + 1))
    [ "$COUNT" -le 20 ] || fail 'legacy hook chain is too deep'
    if [ ! -e "$CUR" ]; then
        BASE_MODE=stock
        break
    fi
    [ -f "$CUR" ] && [ ! -L "$CUR" ] || fail "invalid hook in legacy chain: $CUR"
    case " $SEEN " in *" $CUR "*) fail "legacy hook cycle detected at $CUR";; esac
    SEEN="$SEEN $CUR"

    if grep -q '^# MI-GW2-POST-INIT-API: 1$' "$CUR"; then
        "$CTL" check
        echo 'POST_INIT_ALREADY_MODULAR'
        exit 0
    elif grep -q '^# MI_GW2_BLE_SPEC_CACHE_V1$' "$CUR"; then
        COMPONENTS="$COMPONENTS ble-cache"
        if [ -f /data/ble-spec-cache/original-hook-absent ]; then BASE_MODE=stock; break; fi
        CUR=/data/ble-spec-cache/original-post_init.sh
    elif grep -q '^# MI_GATEWAY2_OTBR_HOST_V1$' "$CUR"; then
        COMPONENTS="$COMPONENTS otbr"
        CUR=/data/otbr/original-post_init.sh
    elif grep -q '^# MI_GATEWAY2_RCP_OPENMIIO_V1$' "$CUR"; then
        CUR=/data/rcp-openmiio/original-post_init.sh
    elif grep -q '^# MI_GATEWAY2_RCP_MODE_V1$' "$CUR"; then
        CUR=/data/rcp-mode/original-post_init.sh
    elif grep -q '^# MI_GATEWAY2_TUN_DEPLOY_V1$' "$CUR"; then
        COMPONENTS="$COMPONENTS tun"
        if [ -f /data/tun/original-hook.state ] && [ "$(cat /data/tun/original-hook.state)" = absent ]; then
            BASE_MODE=stock; break
        fi
        CUR=/data/tun/original-post_init.sh
    elif grep -q '^# MI_GATEWAY2_OPENSSH_DEPLOY_V1$' "$CUR"; then
        COMPONENTS="$COMPONENTS openssh"
        if grep -q '^exec /bin/fw_manager.sh -r' "$CUR"; then BASE_MODE=stock; break; fi
        fail 'OpenSSH legacy hook has an unsupported continuation'
    elif grep -q '^exec /bin/fw_manager.sh -r' "$CUR" || grep -q '^[[:space:]]*/bin/fw_manager.sh -r' "$CUR"; then
        BASE_MODE=stock
        break
    elif [ ! -s "$CUR" ] || awk '
        /^[[:space:]]*($|#)/ { next }
        /^[[:space:]]*exit[[:space:]]+0[[:space:]]*;?[[:space:]]*$/ { exit0=1; next }
        { bad=1 }
        END { exit !(exit0 && !bad) }
    ' "$CUR"; then
        BASE_MODE=stock
        break
    else
        BASE_FILE=$BASE/captured-original.sh
        cp "$CUR" "$BASE/captured-original.sh.new"
        chmod 600 "$BASE/captured-original.sh.new"
        sh -n "$BASE/captured-original.sh.new" || { rm -f "$BASE/captured-original.sh.new"; fail "unknown base hook failed shell syntax: $CUR"; }
        mv -f "$BASE/captured-original.sh.new" "$BASE_FILE"
        BASE_MODE=captured
        echo "POST_INIT_CAPTURED_UNKNOWN_BASE: $CUR"
        break
    fi
done

if [ "$BASE_MODE" = stock ]; then
    "$CTL" install-base stock
else
    "$CTL" install-base captured "$BASE_FILE"
fi

was_detected() {
    case " $COMPONENTS " in *" $1 "*) return 0;; esac
    return 1
}
if was_detected openssh; then "$CTL" add openssh "$MODULES/openssh.sh"; fi
if was_detected tun; then "$CTL" add tun "$MODULES/tun.sh"; fi
if was_detected ble-cache; then "$CTL" add ble-cache "$MODULES/ble-cache.sh"; fi
if was_detected otbr; then "$CTL" add otbr "$MODULES/otbr.sh"; fi
"$CTL" check
sync
echo "POST_INIT_LEGACY_MIGRATED components=$COMPONENTS base=$BASE_MODE"
