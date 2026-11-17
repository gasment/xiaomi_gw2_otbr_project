#!/bin/sh
set -eu
BACKUP=/data/otbr/rcp-recovery-backup
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
[ -f "$BACKUP/ready" ] || { echo 'Recovery script backup missing' >&2; exit 1; }
(cd "$BACKUP" && sha256sum -c SHA256SUMS)
sh /data/otbr/stop.sh
for NAME in supervisor.sh status.sh rcp-recovery.sh; do
    if [ -f "$BACKUP/$NAME" ]; then
        cp "$BACKUP/$NAME" "/data/otbr/$NAME.new"
        chmod 700 "/data/otbr/$NAME.new"
        mv "/data/otbr/$NAME.new" "/data/otbr/$NAME"
    fi
done
# An unused helper may remain when the original supervisor had no recovery feature.
sh /data/otbr/start.sh
echo 'RCP_RECOVERY_ROLLBACK_DONE: previous scripts restored; Host binary and gateway YAML unchanged.'
