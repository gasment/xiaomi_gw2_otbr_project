#!/bin/sh
# Deterministic cleanup for the project-owned files and processes.
set -u

BASE=${GW2_POST_INIT_BASE:-/data/mi-gw2-post-init}
HOOK=${GW2_POST_INIT_HOOK:-/data/scripts/post_init.sh}
AUTH=${GW2_AUTH_FILE:-/res/passwd}
RCP_SESSION=${GW2_RCP_SESSION:-/tmp/rcp-native/state}
MODE=${1:---remove-all}

PROJECT_DIRS="
/data/openssh
/data/tun
/data/rcp-mode
/data/rcp-openmiio
/data/otbr
/data/ble-spec-cache
/data/mi-gw2-post-init
/data/mi-gw2-auto
/data/mi-gw2-gui
"
PROJECT_FILES="
/data/openmiio_agent
/data/openmiio_agent.lua
/data/openmiio_agent.lua.new
/data/openmiio_agent.new
/data/openmiio_agent.previous
/data/scripts/post_init.sh.new
"

say() { printf '%s\n' "$*"; }
fail() { printf 'FACTORY_RESET_ERROR: %s\n' "$*" >&2; exit 1; }

running_pids() {
    for D in /proc/[0-9]*; do
        [ -d "$D" ] || continue
        PID=${D##*/}
        [ "$PID" = "$$" ] && continue
        STATE=$(awk '/^State:/{print $2; exit}' "$D/status" 2>/dev/null || :)
        case "$STATE" in
            Z*) continue ;;
        esac
        EXE=$(readlink "$D/exe" 2>/dev/null || :)
        CMD=$(tr '\000' ' ' <"$D/cmdline" 2>/dev/null || :)
        case "$EXE $CMD" in
            */data/otbr/*|*/data/openmiio_agent*|*/data/ble-spec-cache/*|*/data/openssh/*|*/data/rcp-openmiio/*|*/data/rcp-mode/*)
                printf '%s\n' "$PID"
                ;;
        esac
    done
}

stop_matching() {
    PATTERN=$1
    for D in /proc/[0-9]*; do
        [ -d "$D" ] || continue
        PID=${D##*/}
        [ "$PID" = "$$" ] && continue
        TEXT=$(readlink "$D/exe" 2>/dev/null || :)
        TEXT="$TEXT $(tr '\000' ' ' <"$D/cmdline" 2>/dev/null || :)"
        case "$TEXT" in
            $PATTERN*)
                kill "$PID" 2>/dev/null || :
                say "FACTORY_STOP_PID=$PID"
                ;;
        esac
    done
}

wait_for_runtime_exit() {
    N=0
    while :; do
        PIDS=$(running_pids | tr '\n' ' ')
        [ -z "$PIDS" ] && return 0
        [ "$N" -lt 10 ] || return 1
        sleep 1
        N=$((N + 1))
    done
}

force_stop_runtime() {
    PIDS=$(running_pids | tr '\n' ' ')
    [ -n "$PIDS" ] || return 0
    for PID in $PIDS; do
        kill -TERM "$PID" 2>/dev/null || :
        say "FACTORY_FORCE_STOP_PID=$PID"
    done
    sleep 2
    PIDS=$(running_pids | tr '\n' ' ')
    [ -z "$PIDS" ] && return 0
    for PID in $PIDS; do
        kill -KILL "$PID" 2>/dev/null || :
        say "FACTORY_KILL_PID=$PID"
    done
    sleep 1
}

stop_runtime() {
    FULL=${1:-no}
    [ -x /data/otbr/stop.sh ] && sh /data/otbr/stop.sh >/dev/null 2>&1 || :
    [ -x /data/ble-spec-cache/stop.sh ] && sh /data/ble-spec-cache/stop.sh >/dev/null 2>&1 || :
    if [ -r /tmp/rcp-openmiio.lock/pid ]; then
        PID=$(cat /tmp/rcp-openmiio.lock/pid 2>/dev/null || :)
        case "$PID" in
            ''|*[!0-9]*) ;;
            *)
                TEXT="$(readlink "/proc/$PID/exe" 2>/dev/null || :) $(tr '\000' ' ' <"/proc/$PID/cmdline" 2>/dev/null || :)"
                case "$TEXT" in
                    *'/data/rcp-openmiio/'*) kill "$PID" 2>/dev/null || : ; say "FACTORY_STOP_PID=$PID" ;;
                esac
                ;;
        esac
    fi
    stop_matching '*/data/otbr/*'
    stop_matching '*/data/ble-spec-cache/*'
    stop_matching '*/data/rcp-openmiio/*'
    if [ "$FULL" = yes ]; then
        if [ -r /var/run/openssh-test.pid ]; then
            PID=$(cat /var/run/openssh-test.pid 2>/dev/null || :)
            case "$PID" in
                ''|*[!0-9]*) ;;
                *)
                    [ "$(readlink "/proc/$PID/exe" 2>/dev/null || :)" = /data/openssh/sbin/sshd ] &&
                        kill "$PID" 2>/dev/null || :
                    ;;
            esac
        fi
        stop_matching '*/data/openmiio_agent*'
    fi
    sleep 2
    if ! wait_for_runtime_exit; then
        say "FACTORY_RUNTIME_STILL_RUNNING=$(running_pids | tr '\n' ' ')"
        force_stop_runtime
    fi
}

restore_previous_rcp_session() {
    [ -d "$RCP_SESSION" ] || return 0
    if [ -x /tmp/rcp-native/restore-services.sh ]; then
        sh /tmp/rcp-native/restore-services.sh >/dev/null 2>&1 || \
            say 'FACTORY_WARNING: previous RCP service session could not be resumed cleanly'
    fi
}

remove_owned_modules() {
    [ -x "$BASE/post-initctl.sh" ] || return 0
    for ID in otbr openssh tun ble-cache; do
        GW2_POST_INIT_BASE="$BASE" GW2_POST_INIT_HOOK="$HOOK" \
            "$BASE/post-initctl.sh" remove "$ID" >/dev/null 2>&1 || :
    done
}

restore_hook() {
    [ -e "$HOOK" ] || { say 'POST_INIT_HOOK=absent'; return 0; }
    [ ! -L "$HOOK" ] || fail 'post_init.sh is a symlink; it was left untouched'

    if grep -q '^# MI-GW2-POST-INIT-API: 1$' "$HOOK"; then
        remove_owned_modules
        if grep -q '^# BEGIN MI-GW2 POST-INIT MODULE:' "$HOOK"; then
            fail 'foreign modular post-init entries remain; hook was preserved'
        fi
    fi

    if [ -f "$BASE/captured-original.sh" ]; then
        sh -n "$BASE/captured-original.sh" || fail 'captured original post_init.sh failed syntax validation'
        cp "$BASE/captured-original.sh" "$HOOK.new"
        chmod 755 "$HOOK.new"
        mv -f "$HOOK.new" "$HOOK"
        say 'POST_INIT_HOOK=restored-original'
        return 0
    fi

    if grep -q '^# MI-GW2-POST-INIT-API: 1$' "$HOOK"; then
        rm -f "$HOOK"
        say 'POST_INIT_HOOK=removed-project-stock-anchor'
        return 0
    fi

    say 'POST_INIT_HOOK=preserved-unmanaged'
}

restore_auth_account() {
    [ -f "$AUTH" ] || return 0
    grep -q '^sshd:' "$AUTH" || return 0
    TMP="$AUTH.factory-reset-$$"
    awk -F: '
        BEGIN { OFS=":" }
        $1=="sshd" &&
        $3>=65000 && $3<=65534 &&
        $6=="/var/empty" &&
        $7=="/bin/false" { next }
        { print }
    ' "$AUTH" > "$TMP" || { rm -f "$TMP"; fail 'could not prepare sshd account removal'; }
    cp "$TMP" "$AUTH" || { rm -f "$TMP"; fail 'could not update persistent passwd file'; }
    rm -f "$TMP"
    say 'OPENSSH_SERVICE_ACCOUNT=removed'
}

unmount_project_wrappers() {
    for TARGET in /bin/fw_manager.sh /bin/app_monitor.sh; do
        if awk -v target="$TARGET" '$2 == target { found=1 } END { exit !found }' /proc/mounts; then
            umount "$TARGET" 2>/dev/null || umount -l "$TARGET" 2>/dev/null || :
            if awk -v target="$TARGET" '$2 == target { found=1 } END { exit !found }' /proc/mounts; then
                say "FACTORY_WARNING: bind mount remains on $TARGET until reboot"
            else
                say "FACTORY_UNMOUNTED=$TARGET"
            fi
        fi
    done
}

remove_project_paths() {
    for P in $PROJECT_DIRS $PROJECT_FILES; do
        rm -rf "$P" 2>/dev/null || :
    done
    rm -rf /tmp/rcp-native \
        /tmp/rcp-openmiio.lock \
        /tmp/mi-gw2-auto-work \
        /tmp/mi-otbr-supervisor.lock 2>/dev/null || :
    rm -f /tmp/mi-otbr.pid \
        /tmp/mi-otbr.stop \
        /tmp/rcp-openmiio.stock-ready \
        /tmp/gw2-ble-spec-cache-status.json \
        /tmp/gw2-ble-cache-clock.pid \
        /tmp/gw2-ble-cache-clock.lock \
        /var/run/openssh-test.pid 2>/dev/null || :
}

remove_tun() {
    if [ -c /dev/net/tun ]; then
        USERS=$(fuser /dev/net/tun 2>/dev/null || :)
        if [ -z "$USERS" ]; then
            rm -f /dev/net/tun
        else
            say "FACTORY_WARNING: /dev/net/tun still used by $USERS"
        fi
    fi
    grep -q '^tun ' /proc/modules 2>/dev/null && rmmod tun 2>/dev/null || :
}

verify_clean() {
    RESIDUE=
    for P in $PROJECT_DIRS $PROJECT_FILES; do
        [ ! -e "$P" ] || RESIDUE="$RESIDUE $P"
    done
    [ ! -e /tmp/rcp-native ] || RESIDUE="$RESIDUE /tmp/rcp-native"
    [ ! -e /dev/net/tun ] || RESIDUE="$RESIDUE /dev/net/tun"
    grep -q '^tun ' /proc/modules 2>/dev/null && RESIDUE="$RESIDUE kernel:tun"
    if [ -e "$HOOK" ] && grep -Eq 'MI-GW2-POST-INIT-API|BEGIN MI-GW2 POST-INIT (MODULE|STOCK ANCHOR)' "$HOOK"; then
        RESIDUE="$RESIDUE $HOOK:project-markers"
    fi
    if awk -v target=/bin/fw_manager.sh '$2 == target { found=1 } END { exit !found }' /proc/mounts; then
        RESIDUE="$RESIDUE /bin/fw_manager.sh:bind"
    fi
    if awk -v target=/bin/app_monitor.sh '$2 == target { found=1 } END { exit !found }' /proc/mounts; then
        RESIDUE="$RESIDUE /bin/app_monitor.sh:bind"
    fi
    PIDS=$(running_pids | tr '\n' ' ')
    [ -z "$PIDS" ] || RESIDUE="$RESIDUE managed-pids:$PIDS"
    if [ -n "$RESIDUE" ]; then
        say "FACTORY_RESIDUE=$RESIDUE"
        return 1
    fi
    say 'FACTORY_VERIFY_PASS: no project artifact or managed process remains'
}

status() {
    say "FACTORY_STATUS_BASE=$(test -e "$BASE" && echo present || echo absent)"
    say "FACTORY_STATUS_HOOK=$(test -e "$HOOK" && echo present || echo absent)"
    say "FACTORY_STATUS_PIDS=$(running_pids | tr '\n' ' ')"
    say "FACTORY_STATUS_UART=$(fuser /dev/ttyS1 2>/dev/null || echo none)"
    for P in $PROJECT_DIRS $PROJECT_FILES; do
        [ ! -e "$P" ] || say "FACTORY_STATUS_PRESENT=$P"
    done
    verify_clean
}

case "$MODE" in
    --status)
        status
        ;;
    --prepare-flash)
        restore_previous_rcp_session
        stop_runtime no
        say 'FACTORY_FLASH_RUNTIME_PREPARED'
        ;;
    --restore-hook)
        restore_hook
        sync
        ;;
    --remove-all)
        say 'FACTORY_REMOVE_BEGIN'
        restore_hook
        stop_runtime yes
        unmount_project_wrappers
        remove_tun
        restore_auth_account
        remove_project_paths
        force_stop_runtime
        sync
        verify_clean || exit 1
        say 'FACTORY_REMOVE_OK'
        ;;
    --verify)
        verify_clean
        ;;
    *)
        fail 'usage: factory-reset.sh --status|--prepare-flash|--restore-hook|--remove-all|--verify'
        ;;
esac
