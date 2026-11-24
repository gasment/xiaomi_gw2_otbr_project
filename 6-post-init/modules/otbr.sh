# OTBR preparation is ordered before stock; supervision waits for stock readiness.
[ -x /data/otbr/boot-manager.sh ] || {
    echo 'POST_INIT_MODULE_FAILED: otbr boot manager missing' >>/var/log/otbr-boot-manager.log
}
/data/otbr/boot-manager.sh prepare >>/var/log/otbr-boot-manager.log 2>&1 ||
    echo 'POST_INIT_MODULE_FAILED: otbr prepare' >>/var/log/otbr-boot-manager.log
(
    /data/otbr/boot-manager.sh supervise >>/var/log/otbr-boot-manager.log 2>&1 ||
        echo 'POST_INIT_MODULE_FAILED: otbr supervise' >>/var/log/otbr-boot-manager.log
) &
