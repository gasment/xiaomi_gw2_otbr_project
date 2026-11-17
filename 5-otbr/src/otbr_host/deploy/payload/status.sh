#!/bin/sh
. /data/otbr/common.sh
for FILE in "$SUPERVISOR" "$CHILD_PID"; do
    if [ -r "$FILE" ]; then echo "$FILE: $(cat "$FILE")"; else echo "$FILE: absent"; fi
done
printf 'IPv6 forwarding: '; cat /proc/sys/net/ipv6/conf/all/forwarding
echo 'Last RCP hardware recovery attempt:'
if [ -r /tmp/mi-otbr-rcp-recovery/status ]; then cat /tmp/mi-otbr-rcp-recovery/status; else echo 'none this boot'; fi
echo 'Recent Host log:'
tail -n 35 /var/log/mi-otbr.log 2>/dev/null
