#!/bin/sh
set -eu

BASE=${GW2_POST_INIT_BASE:-/data/mi-gw2-post-init}
HOOK=${GW2_POST_INIT_HOOK:-/data/scripts/post_init.sh}
LOCK=${GW2_POST_INIT_LOCK:-/tmp/mi-gw2-post-init.lock}
ANCHOR_BEGIN='# BEGIN MI-GW2 POST-INIT STOCK ANCHOR'
ANCHOR_END='# END MI-GW2 POST-INIT STOCK ANCHOR'

fail() { echo "POST_INIT_ERROR: $*" >&2; exit 1; }

count_line() {
    awk -v wanted="$1" '$0 == wanted { n++ } END { print n + 0 }' "$2"
}

lock() {
    if mkdir "$LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCK/pid"
        trap 'rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || :' EXIT HUP INT TERM
        return
    fi
    [ -r "$LOCK/pid" ] || fail 'post-init lock exists without a PID; inspect it manually'
    PID=$(cat "$LOCK/pid")
    case "$PID" in ''|*[!0-9]*) fail 'post-init lock has an invalid PID';; esac
    kill -0 "$PID" 2>/dev/null && fail "another post-init update is running: $PID"
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null || fail 'stale post-init lock contains unexpected files'
    mkdir "$LOCK"
    printf '%s\n' "$$" > "$LOCK/pid"
    trap 'rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || :' EXIT HUP INT TERM
}

write_anchor() {
    cat > "$BASE/anchor.sh" <<'EOF'
# BEGIN MI-GW2 POST-INIT STOCK ANCHOR
# Keep this block last. Component modules belong above it.
mkdir -p /tmp/mi-gw2-post-init
rm -f /tmp/mi-gw2-post-init/stock.ready /tmp/mi-gw2-post-init/stock.failed
if [ -f /data/mi-gw2-post-init/captured-original.sh ]; then
    sh /data/mi-gw2-post-init/captured-original.sh
else
    /bin/fw_manager.sh -r
fi
RC=$?
if [ "$RC" -eq 0 ]; then
    touch /tmp/mi-gw2-post-init/stock.ready
else
    touch /tmp/mi-gw2-post-init/stock.failed
fi
exit "$RC"
# END MI-GW2 POST-INIT STOCK ANCHOR
EOF
    chmod 600 "$BASE/anchor.sh"
}

write_base_mode() {
    MODE_VALUE=$1
    case "$MODE_VALUE" in stock|captured) ;; *) fail "invalid base mode: $MODE_VALUE" ;; esac
    printf '%s\n' "$MODE_VALUE" > "$BASE/base-mode.new"
    chmod 600 "$BASE/base-mode.new"
    mv -f "$BASE/base-mode.new" "$BASE/base-mode"
}

write_new_hook() {
    cat > "$HOOK.new" <<'EOF'
#!/bin/sh
# MI-GW2-POST-INIT-API: 1
# This file is a visible startup manifest. Each component owns only its
# BEGIN/END module block. The stock anchor must remain the final block.
EOF
    cat "$BASE/anchor.sh" >> "$HOOK.new"
    chmod 755 "$HOOK.new"
    sh -n "$HOOK.new" || { rm -f "$HOOK.new"; fail 'generated post_init.sh failed shell syntax'; }
    mv -f "$HOOK.new" "$HOOK"
}

ensure_base() {
    HOOK_DIR=${HOOK%/*}
    mkdir -p "$BASE" "$HOOK_DIR"
    chmod 700 "$BASE"
    write_anchor
    if [ ! -f "$BASE/base-mode" ]; then
        if [ -f "$BASE/captured-original.sh" ]; then
            write_base_mode captured
        else
            write_base_mode stock
        fi
    fi
    if [ ! -e "$HOOK" ]; then
        write_new_hook
        return
    fi
    [ ! -L "$HOOK" ] || fail 'post_init.sh must not be a symlink'
    [ "$(count_line '# MI-GW2-POST-INIT-API: 1' "$HOOK")" -eq 1 ] || fail 'post_init.sh is not a modular API 1 manifest; run migrate-legacy explicitly'
    [ "$(count_line "$ANCHOR_BEGIN" "$HOOK")" -eq 1 ] || fail 'stock anchor BEGIN marker is missing or duplicated'
    [ "$(count_line "$ANCHOR_END" "$HOOK")" -eq 1 ] || fail 'stock anchor END marker is missing or duplicated'
    awk -v a="$ANCHOR_BEGIN" -v b="$ANCHOR_END" '
        $0==a { inside=1; next }
        $0==b { inside=0; found=1; next }
        inside || !found { next }
        /^[[:space:]]*($|#)/ { next }
        { exit 1 }
    ' "$HOOK" || fail 'stock anchor is not the final executable block'
    sh -n "$HOOK" || fail 'post_init.sh failed shell syntax validation'
}

validate_id() {
    case "$1" in ''|*[!a-z0-9-]*|[!a-z]*) fail 'module ID must use lowercase letters, digits and hyphens';; esac
}

replace_or_insert() {
    ID=$1
    BODY=$2
    BEGIN="# BEGIN MI-GW2 POST-INIT MODULE: $ID"
    END="# END MI-GW2 POST-INIT MODULE: $ID"
    [ -f "$BODY" ] || fail "module body not found: $BODY"
    sh -n "$BODY" || fail "module body failed shell syntax: $ID"
    grep -F -q "$ANCHOR_BEGIN" "$BODY" && fail "module body contains the stock anchor: $ID"
    grep -F -q 'MI-GW2 POST-INIT MODULE:' "$BODY" && fail "module body contains nested module markers: $ID"
    [ "$(count_line "$BEGIN" "$HOOK")" -le 1 ] || fail "module BEGIN marker duplicated: $ID"
    [ "$(count_line "$END" "$HOOK")" -le 1 ] || fail "module END marker duplicated: $ID"
    awk -v begin="$BEGIN" -v end="$END" -v body="$BODY" -v anchor="$ANCHOR_BEGIN" '
        $0 == begin {
            if (inside || seen) bad=1
            inside=1; seen=1; print; while ((getline line < body) > 0) print line; close(body); next
        }
        $0 == end {
            if (!inside) bad=1
            inside=0; print; next
        }
        inside { next }
        $0 == anchor && !seen {
            print begin; while ((getline line < body) > 0) print line; close(body); print end; seen=1
        }
        { print }
        END { if (bad || inside || !seen) exit 1 }
    ' "$HOOK" > "$HOOK.new" || { rm -f "$HOOK.new"; fail "could not update module: $ID"; }
    chmod 755 "$HOOK.new"
    sh -n "$HOOK.new" || { rm -f "$HOOK.new"; fail "updated post_init failed shell syntax: $ID"; }
    mv -f "$HOOK.new" "$HOOK"
}

remove_module() {
    ID=$1
    BEGIN="# BEGIN MI-GW2 POST-INIT MODULE: $ID"
    END="# END MI-GW2 POST-INIT MODULE: $ID"
    CB=$(count_line "$BEGIN" "$HOOK")
    CE=$(count_line "$END" "$HOOK")
    [ "$CB" -eq "$CE" ] || fail "module markers are unbalanced: $ID"
    [ "$CB" -le 1 ] || fail "module markers are duplicated: $ID"
    [ "$CB" -eq 1 ] || return 0
    awk -v begin="$BEGIN" -v end="$END" '
        $0 == begin { inside=1; seen=1; next }
        $0 == end && inside { inside=0; next }
        inside { next }
        { print }
        END { if (inside || !seen) exit 1 }
    ' "$HOOK" > "$HOOK.new" || { rm -f "$HOOK.new"; fail "could not remove module: $ID"; }
    chmod 755 "$HOOK.new"
    sh -n "$HOOK.new" || { rm -f "$HOOK.new"; fail "post_init failed shell syntax after removing $ID"; }
    mv -f "$HOOK.new" "$HOOK"
}

install_base() {
    MODE=$1
    SOURCE=${2:-}
    STAMP=$(date +%Y%m%d-%H%M%S)-$PPID
    mkdir -p "$BASE/backups/$STAMP"
    if [ -e "$HOOK" ]; then
        [ ! -L "$HOOK" ] || fail 'refusing to back up a symlink post_init.sh'
        cp -p "$HOOK" "$BASE/backups/$STAMP/post_init.sh"
    fi
    case "$MODE" in
        stock)
            rm -f "$BASE/captured-original.sh"
            write_base_mode stock
            ;;
        captured)
            [ -n "$SOURCE" ] && [ -f "$SOURCE" ] || fail 'captured base file is required'
            cp "$SOURCE" "$BASE/captured-original.sh.new"
            chmod 600 "$BASE/captured-original.sh.new"
            sh -n "$BASE/captured-original.sh.new" || { rm -f "$BASE/captured-original.sh.new"; fail 'captured base failed shell syntax'; }
            mv -f "$BASE/captured-original.sh.new" "$BASE/captured-original.sh"
            write_base_mode captured
            ;;
        *) fail 'base mode must be stock or captured' ;;
    esac
    write_anchor
    write_new_hook
    echo "POST_INIT_BASE_INSTALLED: $MODE backup=$STAMP"
}

check_modules() {
    awk '
        /^# BEGIN MI-GW2 POST-INIT MODULE: [a-z0-9-]+$/ {
            id=$0; sub(/^# BEGIN MI-GW2 POST-INIT MODULE: /,"",id)
            if (open != "") bad=1
            counts[id]++; open=id; next
        }
        /^# END MI-GW2 POST-INIT MODULE: [a-z0-9-]+$/ {
            id=$0; sub(/^# END MI-GW2 POST-INIT MODULE: /,"",id)
            if (open != id) bad=1
            ends[id]++; open=""; next
        }
        END {
            if (open != "") bad=1
            for (id in counts) if (counts[id] != 1 || ends[id] != 1) bad=1
            for (id in ends) if (counts[id] != 1 || ends[id] != 1) bad=1
            if (bad) exit 1
        }
    ' "$HOOK" || fail 'module BEGIN/END markers are malformed or duplicated'
}

usage() {
    cat <<'EOF'
Usage: post-initctl.sh COMMAND [ARGS]
  ensure
  install-base stock|captured [BASE_FILE]
  add ID BODY_FILE
  remove ID
  list
  check
EOF
}

[ "$#" -ge 1 ] || { usage >&2; exit 2; }
COMMAND=$1
shift
case "$COMMAND" in
    ensure) [ "$#" -eq 0 ] || { usage >&2; exit 2; }; lock; ensure_base; sync; echo 'POST_INIT_MODULE_MANIFEST_READY' ;;
    install-base)
        [ "$#" -eq 1 ] || [ "$#" -eq 2 ] || { usage >&2; exit 2; }
        lock; install_base "$@" ;;
    add)
        [ "$#" -eq 2 ] || { usage >&2; exit 2; }
        validate_id "$1"; lock; ensure_base; replace_or_insert "$1" "$2"; sync; echo "POST_INIT_MODULE_UPSERTED: $1" ;;
    remove)
        [ "$#" -eq 1 ] || { usage >&2; exit 2; }
        validate_id "$1"; lock; ensure_base; remove_module "$1"; sync; echo "POST_INIT_MODULE_REMOVED: $1" ;;
    list) [ "$#" -eq 0 ] || { usage >&2; exit 2; }; sed -n 's/^# BEGIN MI-GW2 POST-INIT MODULE: \(.*\)$/\1/p' "$HOOK" ;;
    check)
        [ "$#" -eq 0 ] || { usage >&2; exit 2; }
        ensure_base
        check_modules
        awk '/^# BEGIN MI-GW2 POST-INIT MODULE:/ { n++ } END { print "POST_INIT_MODULES=" n + 0 }' "$HOOK"
        echo 'POST_INIT_MANIFEST_VALID' ;;
    *) usage >&2; exit 2;;
esac
