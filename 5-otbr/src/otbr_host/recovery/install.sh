#!/bin/sh
set -eu
PACKAGE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$PACKAGE"
[ "$(id -u)" = 0 ] || { echo 'Run as root' >&2; exit 1; }
for TOOL in sha256sum cp mv mkdir chmod grep cat fuser usleep sh; do
    command -v "$TOOL" >/dev/null 2>&1 || { echo "Missing tool: $TOOL" >&2; exit 1; }
done
sha256sum -c SHA256SUMS
sha256sum -c compatibility.sha256
CURRENT=$(sha256sum /data/otbr/supervisor.sh)
CURRENT=${CURRENT%% *}
grep -qx "$CURRENT" accepted-supervisor.sha256 || { echo 'Supervisor has independent changes; merge before updating.' >&2; exit 1; }
for NAME in supervisor.sh status.sh rcp-recovery.sh; do sh -n "payload/$NAME"; done
sh /data/otbr/check.sh
BACKUP=/data/otbr/rcp-recovery-backup
[ ! -L "$BACKUP" ] || { echo 'Invalid backup path' >&2; exit 1; }
if [ -f "$BACKUP/ready" ]; then
    (cd "$BACKUP" && sha256sum -c SHA256SUMS)
else
    mkdir -p "$BACKUP"
    chmod 700 "$BACKUP"
    for NAME in supervisor.sh status.sh rcp-recovery.sh; do
        if [ -f "/data/otbr/$NAME" ]; then cp "/data/otbr/$NAME" "$BACKUP/$NAME"; fi
    done
    cp rollback.sh "$BACKUP/rollback.sh"
    (cd "$BACKUP" && sha256sum ./*.sh > SHA256SUMS)
    touch "$BACKUP/ready"
fi
ROLLBACK_NEEDED=0
on_exit() {
    RESULT=$?
    trap - EXIT INT TERM
    if [ "$RESULT" -ne 0 ] && [ "$ROLLBACK_NEEDED" -eq 1 ]; then
        echo 'Script update failed; restoring the previous supervisor.'
        sh "$BACKUP/rollback.sh" || echo 'Automatic script rollback failed; inspect logs before restarting.'
    fi
    exit "$RESULT"
}
trap on_exit EXIT
trap 'exit 1' INT TERM
sh /data/otbr/stop.sh
ROLLBACK_NEEDED=1
# Install helper before the supervisor that sources it. Host binary/config remain untouched.
for NAME in rcp-recovery.sh status.sh supervisor.sh; do
    cp "payload/$NAME" "/data/otbr/$NAME.new"
    chmod 700 "/data/otbr/$NAME.new"
    mv "/data/otbr/$NAME.new" "/data/otbr/$NAME"
done
sh /data/otbr/start.sh
ROLLBACK_NEEDED=0
echo 'RCP_RECOVERY_UPDATE_INSTALLED: scripts updated; existing Host binary and gateway YAML preserved.'
echo 'Status: sh /data/otbr/status.sh'
echo 'Rollback: sh /data/otbr/rcp-recovery-backup/rollback.sh'
