#!/bin/sh
# MI_GATEWAY2_RCP_OPENMIIO_V1
mkdir -p /var/log
# Keep the supervisor visible before networking and HA preparation can finish.
/data/rcp-openmiio/start.sh >> /var/log/rcp-openmiio-start.log 2>&1
/data/rcp-openmiio/original-post_init.sh
RC=$?
if [ "$RC" -eq 0 ]; then
    touch /tmp/rcp-openmiio.stock-ready
else
    echo "ERROR: stock startup returned $RC; openmiio was not started." >> /var/log/rcp-openmiio-start.log
fi
exit "$RC"
