#!/bin/sh
set -eu
BASE=/data/ble-spec-cache
STATUS=/tmp/gw2-ble-spec-cache-status.json
case "${1:-}" in
    --json) [ -r "$STATUS" ] || { echo 'Status is not ready.' >&2; exit 1; }; cat "$STATUS"; echo; exit 0;;
    '') ;;
    *) echo 'Usage: status.sh [--json]' >&2; exit 2;;
esac
if [ -f "$BASE/disabled" ]; then echo 'PATCH_DISABLED'; fi
if cmp -s "$BASE/openmiio_agent.lua" /data/openmiio_agent.lua; then echo 'LUA_LOADER_INSTALLED'; else echo 'LUA_LOADER_NOT_ACTIVE'; fi
if [ -r /tmp/gw2-ble-cache-clock.pid ]; then
    PID=$(cat /tmp/gw2-ble-cache-clock.pid)
    case "$PID" in ''|*[!0-9]*) echo 'CLOCK_PID_INVALID';; *)
        if kill -0 "$PID" 2>/dev/null && [ "$(readlink "/proc/$PID/exe")" = "$BASE/ble-cache-clock" ]; then echo "CLOCK_RUNNING pid=$PID"; else echo 'CLOCK_NOT_RUNNING'; fi;;
    esac
else echo 'CLOCK_NOT_RUNNING'; fi
if [ -r "$STATUS" ]; then
    if command -v awk >/dev/null 2>&1; then
        awk '
        function indent( k) { for (k=0;k<depth;k++) printf "  " }
        {
            for (i=1;i<=length($0);i++) {
                c=substr($0,i,1)
                if (quoted) {
                    printf "%s",c
                    if (escaped) escaped=0
                    else if (c=="\\") escaped=1
                    else if (c=="\"") quoted=0
                } else if (c=="\"") { quoted=1; printf "%s",c }
                else if (c=="{" || c=="[") { printf "%s\n",c; depth++; indent() }
                else if (c=="}" || c=="]") { printf "\n"; depth--; indent(); printf "%s",c }
                else if (c==",") { printf ",\n"; indent() }
                else if (c==":") printf ": "
                else if (c !~ /[[:space:]]/) printf "%s",c
            }
        }
        END { printf "\n" }
        ' "$STATUS"
    else
        cat "$STATUS"; echo
    fi
else echo 'LUA_STATUS_NOT_READY'; fi
