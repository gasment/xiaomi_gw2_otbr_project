# OpenSSH failure must never stop the stock startup anchor.
(
    /data/openssh/start-ssh.sh >>/var/log/openssh-start.log 2>&1 ||
        echo 'POST_INIT_MODULE_FAILED: openssh' >>/var/log/openssh-start.log
) &
