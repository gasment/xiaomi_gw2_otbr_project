#!/bin/sh
# MI_GATEWAY2_TUN_DEPLOY_V1
# Always continue to the previous boot hook or the stock launcher.
mkdir -p /var/log
/data/tun/start-tun.sh >> /var/log/tun-start.log 2>&1
if [ -x /data/tun/original-post_init.sh ]; then
    exec /data/tun/original-post_init.sh
fi
exec /bin/fw_manager.sh -r
