# TUN failure must never stop the stock startup anchor.
(
    /data/tun/start-tun.sh >>/var/log/tun-start.log 2>&1 ||
        echo 'POST_INIT_MODULE_FAILED: tun' >>/var/log/tun-start.log
) &
