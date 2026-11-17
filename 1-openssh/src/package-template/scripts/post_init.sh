#!/bin/sh
# MI_GATEWAY2_OPENSSH_DEPLOY_V1
# SSH failure must not block Xiaomi services.
/data/openssh/start-ssh.sh >> /var/log/openssh-start.log 2>&1 &
exec /bin/fw_manager.sh -r
