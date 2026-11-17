#!/bin/sh
# MI_GATEWAY2_OTBR_HOST_V1
(trap '' HUP; sleep 1; /data/otbr/start.sh >> /var/log/mi-otbr-start.log 2>&1) &
exec /data/otbr/original-post_init.sh "$@"
