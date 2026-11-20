#!/bin/sh
set -eu

[ "$#" -eq 4 ] || {
    echo "Usage: patch-launchers.sh FWM_IN FWM_OUT APP_IN APP_OUT" >&2
    exit 2
}

FWM_IN=$1
FWM_OUT=$2
APP_IN=$3
APP_OUT=$4

patch_fw_manager() {
    awk '
        function comment(line) {
            sub(/^[[:space:]]*/, "", line)
            return "# RCP mode disabled: " line
        }
        $0 == "coordinator_ota()" {
            print
            if ((getline nextline) <= 0 || nextline != "{") bad=1
            print nextline
            print "    echo \"RCP mode: stock coordinator OTA skipped\""
            print "    return 0"
            ota=1
            next
        }
        /^[[:space:]]*m?Z3GatewayHost_MQTT[[:space:]]+-p[[:space:]]+\/dev\/ttyS1/ {
            print comment($0)
            zigbee++
            next
        }
        /^[[:space:]]*mzigbee_agent[[:space:]]+-f[[:space:]]+\/etc\/mzigbeeAgent.conf/ {
            print comment($0)
            agent++
            next
        }
        { print }
        END {
            if (bad || ota != 1 || zigbee < 1 || agent < 1) exit 1
        }
    ' "$FWM_IN" > "$FWM_OUT"
}

patch_app_monitor() {
    awk '
        function insert_guard(name) {
            found[name]++
            print
            if ((getline nextline) <= 0 || nextline != "{") bad=1
            print nextline
            print "    return 0 # RCP mode: do not restart stock Zigbee services"
        }
        $0 == "handler_mZ3GatewayHost_MQTT_leaved()" { insert_guard("zigbee"); next }
        $0 == "handler_mzigbee_agent_leaved()" { insert_guard("agent"); next }
        { print }
        END {
            if (bad || found["zigbee"] != 1 || found["agent"] != 1) exit 1
        }
    ' "$APP_IN" > "$APP_OUT"
}

if grep -q 'RCP mode: stock coordinator OTA skipped' "$FWM_IN" &&
   grep -q 'RCP mode: do not restart stock Zigbee services' "$APP_IN"; then
    cp "$FWM_IN" "$FWM_OUT"
    cp "$APP_IN" "$APP_OUT"
    echo 'RCP launchers already isolated; copied current versions.'
    exit 0
fi

patch_fw_manager || {
    rm -f "$FWM_OUT" "$APP_OUT"
    echo 'Unsupported fw_manager.sh structure; install aborted.' >&2
    exit 1
}
patch_app_monitor || {
    rm -f "$FWM_OUT" "$APP_OUT"
    echo 'Unsupported app_monitor.sh structure; install aborted.' >&2
    exit 1
}

sh -n "$FWM_OUT"
sh -n "$APP_OUT"
chmod 700 "$FWM_OUT" "$APP_OUT"
echo 'RCP compatibility patch generated from current stock launchers.'
