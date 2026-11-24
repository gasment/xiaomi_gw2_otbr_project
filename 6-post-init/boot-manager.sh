#!/bin/sh
# MI-GW2 OTBR BOOT MANAGER
# This module owns only the OTBR/RCP stack. It must never alter stock startup.
set -u
LOG=/var/log/otbr-boot-manager.log
STOCK_READY=/tmp/mi-gw2-post-init/stock.ready
STOCK_FAILED=/tmp/mi-gw2-post-init/stock.failed
PREPARED=/tmp/mi-gw2-post-init/otbr.prepared
RCP_READY=/tmp/rcp-openmiio.stock-ready
MODE=${1:-supervise}
mkdir -p /var/log /tmp/mi-gw2-post-init
log() { printf '%s\n' "$*" >> "$LOG"; }
component_fail() { log "OTBR_BOOT_BLOCKED: $*"; exit 0; }
prepare() {
    rm -f "$PREPARED" "$RCP_READY"
    [ -f /data/otbr/enabled ] || component_fail 'OTBR is disabled'
    [ -x /data/rcp-mode/apply-mode.sh ] || component_fail 'RCP mode helper is missing'
    [ -x /data/rcp-openmiio/start.sh ] || component_fail 'RCP/openmiio supervisor is missing'
    [ -x /data/otbr/start.sh ] || component_fail 'OTBR start helper is missing'
    if ! /data/rcp-mode/apply-mode.sh >> "$LOG" 2>&1; then component_fail 'RCP mode failed; stock startup is unaffected'; fi
    if ! /data/rcp-openmiio/start.sh >> "$LOG" 2>&1; then component_fail 'RCP/openmiio supervisor failed; stock startup is unaffected'; fi
    touch "$PREPARED"
    log 'OTBR pre-stock preparation complete'
}
supervise() {
    [ -f "$PREPARED" ] || { log 'OTBR supervision skipped: preparation incomplete'; exit 0; }
    log 'Waiting for stock startup completion marker'
    while [ ! -f "$STOCK_READY" ] && [ ! -f "$STOCK_FAILED" ]; do sleep 2; done
    [ -f "$STOCK_FAILED" ] && component_fail 'stock startup reported failure; OTBR remains stopped'
    touch "$RCP_READY"
    log 'Stock startup complete; allowing BLE/Mesh supervision'
    if ! /data/otbr/start.sh >> "$LOG" 2>&1; then component_fail 'OTBR start failed; stock startup remains unaffected'; fi
    log 'OTBR boot manager completed'
}
case "$MODE" in
    prepare) prepare ;;
    supervise) supervise ;;
    --now) prepare; [ -f "$PREPARED" ] || exit 0; touch "$STOCK_READY"; supervise ;;
    *) component_fail "unknown mode: $MODE" ;;
esac
