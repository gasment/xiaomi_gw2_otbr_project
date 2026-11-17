#!/bin/sh
# Sourced by supervisor.sh. No GPIO operation occurs merely by sourcing this file.
RCP_RECOVERY_DIR=/tmp/mi-otbr-rcp-recovery
RCP_HISTORY=$RCP_RECOVERY_DIR/attempts
RCP_STATUS=$RCP_RECOVERY_DIR/status
RCP_PENDING_RC=
RCP_FAULT_AT=0
RCP_RESET_ASSERTED=0
RCP_LAST_EVENT=

rcp_log() {
    if [ "$RCP_LAST_EVENT" != "$1" ]; then
        echo "RCP_RECOVERY: $2"
        RCP_LAST_EVENT=$1
    fi
}
rcp_now() {
    read RCP_UPTIME RCP_UNUSED < /proc/uptime || return 1
    RCP_NOW=${RCP_UPTIME%%.*}
    case "$RCP_NOW" in ''|*[!0-9]*) return 1;; esac
}
rcp_recovery_init() {
    [ ! -L "$RCP_RECOVERY_DIR" ] || return 1
    (umask 077; mkdir -p "$RCP_RECOVERY_DIR") || return 1
    chmod 700 "$RCP_RECOVERY_DIR" || return 1
}
rcp_queue_recovery() {
    case "$1" in 4|6) ;; *) return 1;; esac
    RCP_PENDING_RC=$1
    if rcp_now; then RCP_FAULT_AT=$RCP_NOW; else RCP_FAULT_AT=0; fi
    RCP_LAST_EVENT=
    rcp_log queued "queued after RCP exit=$1; awaiting exclusive UART and backoff"
}
rcp_history_read() {
    RCP_COUNT=0
    RCP_OLDEST=0
    RCP_LAST_ATTEMPT=0
    RCP_TIMES=
    [ ! -L "$RCP_HISTORY" ] || return 1
    [ -f "$RCP_HISTORY" ] || return 0
    while IFS= read -r RCP_ENTRY || [ -n "$RCP_ENTRY" ]; do
        case "$RCP_ENTRY" in ''|*[!0-9]*) return 1;; esac
        [ "$RCP_ENTRY" -le "$RCP_NOW" ] || return 1
        if [ $((RCP_NOW - RCP_ENTRY)) -lt 600 ]; then
            if [ "$RCP_COUNT" -eq 0 ]; then RCP_OLDEST=$RCP_ENTRY; fi
            RCP_COUNT=$((RCP_COUNT + 1))
            RCP_LAST_ATTEMPT=$RCP_ENTRY
            RCP_TIMES="$RCP_TIMES $RCP_ENTRY"
        fi
    done < "$RCP_HISTORY"
}
rcp_attempt_record() {
    [ ! -L "$RCP_HISTORY.new" ] || return 1
    (umask 077
        for RCP_ENTRY in $RCP_TIMES; do printf '%s\n' "$RCP_ENTRY"; done
        printf '%s\n' "$RCP_NOW"
    ) > "$RCP_HISTORY.new" || return 1
    mv "$RCP_HISTORY.new" "$RCP_HISTORY" || return 1
    RCP_ATTEMPT=$((RCP_COUNT + 1))
}
rcp_status() {
    [ ! -L "$RCP_STATUS" ] || return 1
    (umask 077; printf 'uptime=%s exit=%s attempt=%s/3 result=%s\n' \
        "$RCP_NOW" "$RCP_PENDING_RC" "$RCP_ATTEMPT" "$1" > "$RCP_STATUS")
}
rcp_gpio_is() {
    [ "$(cat "/sys/class/gpio/gpio$1/direction" 2>/dev/null)" = out ] &&
        [ "$(cat "/sys/class/gpio/gpio$1/value" 2>/dev/null)" = "$2" ]
}
rcp_release_reset() {
    # Also used by supervisor's signal/exit cleanup after an interrupted pulse.
    sh /bin/zigbee_reset.sh 0 && rcp_gpio_is 44 0 || return 1
    RCP_RESET_ASSERTED=0
}
rcp_uart_free() {
    [ -c /dev/ttyS1 ] || return 1
    if RCP_USERS=$(fuser /dev/ttyS1 2>&1); then RCP_FUSER_RC=0; else RCP_FUSER_RC=$?; fi
    # BusyBox fuser returns 1 with no output when there are no holders.
    [ "$RCP_FUSER_RC" -eq 1 ] && [ -z "$RCP_USERS" ]
}
rcp_service_wanted() {
    [ -f "$BASE/enabled" ] && [ ! -f "$STOP" ] && [ -f /tmp/rcp-openmiio.stock-ready ]
}
rcp_recover_pending() {
    # 0=recovered, 1=deferred, 2=attempt failed, 3=reset cannot be released.
    case "$RCP_PENDING_RC" in 4|6) ;; *) return 1;; esac
    rcp_service_wanted || return 1
    if ! rcp_now || ! rcp_history_read; then
        rcp_log history "invalid monotonic clock/history; no GPIO operation"
        return 1
    fi
    if [ "$RCP_COUNT" -ge 3 ]; then
        rcp_log limited "limit reached (3 attempts/600s); Host held until budget expires"
        return 1
    fi
    case "$RCP_COUNT" in 0) RCP_DELAY=5;; 1) RCP_DELAY=15;; *) RCP_DELAY=30;; esac
    RCP_NOT_BEFORE=$((RCP_FAULT_AT + RCP_DELAY))
    if [ $((RCP_LAST_ATTEMPT + RCP_DELAY)) -gt "$RCP_NOT_BEFORE" ]; then
        RCP_NOT_BEFORE=$((RCP_LAST_ATTEMPT + RCP_DELAY))
    fi
    if [ "$RCP_NOW" -lt "$RCP_NOT_BEFORE" ]; then
        rcp_log backoff "waiting ${RCP_DELAY}s backoff; no GPIO operation"
        return 1
    fi
    if [ -r "$CHILD_PID" ] && pid_matches "$(cat "$CHILD_PID")" host; then
        rcp_log host "Host still running; no GPIO operation"
        return 1
    fi
    if ! command -v usleep >/dev/null 2>&1 || ! command -v fuser >/dev/null 2>&1 ||
       [ ! -r /bin/zigbee_isp.sh ] || [ ! -r /bin/zigbee_reset.sh ]; then
        rcp_log tools "reset tools/scripts unavailable; no GPIO operation"
        return 1
    fi
    if ! rcp_uart_free || ! rcp_service_wanted; then
        rcp_log uart "UART occupied/unavailable or service stopping; no GPIO operation"
        return 1
    fi
    rcp_attempt_record || { rcp_log storage "cannot record recovery budget; no GPIO operation"; return 1; }
    rcp_status started || return 2
    RCP_LAST_EVENT=
    rcp_log resetting "attempt=$RCP_ATTEMPT/3 exit=$RCP_PENDING_RC normal-application reset"
    if ! sh /bin/zigbee_isp.sh 1 || ! rcp_gpio_is 43 1; then
        rcp_status boot-mode-failed || :
        rcp_log boot "normal boot mode readback failed; reset not asserted"
        return 2
    fi
    if ! rcp_service_wanted || ! rcp_uart_free; then
        rcp_status cancelled || :
        return 1
    fi
    # Set before asserting so cleanup releases even on an interrupted/failed write.
    RCP_RESET_ASSERTED=1
    RCP_PULSE_OK=1
    sh /bin/zigbee_reset.sh 1 && rcp_gpio_is 44 1 || RCP_PULSE_OK=0
    usleep 100000 || RCP_PULSE_OK=0
    if ! rcp_release_reset; then
        rcp_status reset-release-failed || :
        rcp_log release "ERROR: reset release readback failed; refusing to start Host"
        return 3
    fi
    if [ "$RCP_PULSE_OK" -ne 1 ]; then
        rcp_status reset-pulse-failed || :
        rcp_log pulse "reset pulse failed; release verified, Host remains stopped"
        return 2
    fi
    usleep 500000 || return 2
    rcp_status reset-complete || return 2
    rcp_log complete "reset complete; ISP=1 RESET=0 verified; Host may restart"
    RCP_PENDING_RC=
    return 0
}
