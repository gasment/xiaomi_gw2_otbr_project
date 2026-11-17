#!/bin/sh
# MI_GATEWAY2_RCP_MODE_V1
mkdir -p /var/log
if ! /data/rcp-mode/apply-mode.sh >> /var/log/rcp-mode.log 2>&1; then
    echo 'ERROR: RCP isolation failed. Continuing the previous boot chain for recovery.' >> /var/log/rcp-mode.log
fi
exec /data/rcp-mode/original-post_init.sh
