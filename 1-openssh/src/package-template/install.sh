#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run this installer as root on the gateway.'
[ -x /bin/fw_manager.sh ] || fail 'Xiaomi stock service launcher not found.'
command -v agetprop >/dev/null 2>&1 || fail 'Not a supported Xiaomi stock system.'
agetprop | grep -Eq '\[ro.sys.model\]: \[lumi.gateway.(mcn001|mgl001)\]' || fail 'Unsupported gateway model.'
echo 'Checking deployment files...'
sha256sum -c SHA256SUMS || fail 'File verification failed.'
sh -n scripts/start-ssh.sh
sh -n scripts/post_init.sh

HOOK=/data/scripts/post_init.sh
if [ -e "$HOOK" ]; then
    if grep -q 'MI_GATEWAY2_OPENSSH_DEPLOY_V1' "$HOOK"; then
        :
    elif grep -q '/data/openssh/sbin/sshd' "$HOOK" && grep -q '^exec /bin/fw_manager.sh -r' "$HOOK"; then
        # Recognise the simple hook already validated in this project.
        :
    else
        fail 'An unrelated post_init.sh exists. Preserve/merge it manually before installing.'
    fi
fi

FREE_KB=$(df -Pk /data | awk 'END {print $4}')
[ "$FREE_KB" -ge 18000 ] || fail 'At least 18000 KiB free space is required on /data.'
[ -w /res/passwd ] || fail '/res/passwd is not writable.'
if grep -q '^sshd:' /etc/passwd; then
    awk -F: '$1 == "sshd" {if ($3 <= 0 || $4 <= 0) exit 1}' /etc/passwd || fail 'sshd must be an unprivileged account.'
fi

STAMP=$(date +%Y%m%d-%H%M%S)-$$
BACKUP=/data/openssh/backups/$STAMP
mkdir -p "$BACKUP" /data/openssh/bin /data/openssh/sbin /data/openssh/libexec /data/openssh/etc /data/scripts
cp /res/passwd "$BACKUP/passwd"
if [ -e "$HOOK" ]; then cp -p "$HOOK" "$BACKUP/post_init.sh"; fi
if [ -e /data/openssh/etc/sshd_config ]; then cp -p /data/openssh/etc/sshd_config "$BACKUP/sshd_config"; fi

# Never change root's password. Only add the locked privilege-separation account.
if ! grep -q '^sshd:' /etc/passwd; then
    UID_NUM=65534
    while awk -F: -v n="$UID_NUM" '$3 == n || $4 == n {found=1} END {exit !found}' /etc/passwd; do
        UID_NUM=$((UID_NUM - 1))
        [ "$UID_NUM" -ge 65000 ] || fail 'No free service UID/GID in 65000..65534.'
    done
    printf '\nsshd:*:%s:%s:OpenSSH privilege separation:/var/empty:/bin/false\n' "$UID_NUM" "$UID_NUM" >> /res/passwd
fi

# Atomic per-file replacement avoids truncating a running executable.
put() {
    cp "$1" "$2.new"
    chmod "$3" "$2.new"
    mv -f "$2.new" "$2"
}
put payload/sbin/sshd /data/openssh/sbin/sshd 755
put payload/libexec/sshd-session /data/openssh/libexec/sshd-session 755
put payload/libexec/sshd-auth /data/openssh/libexec/sshd-auth 755
put payload/bin/ssh-keygen /data/openssh/bin/ssh-keygen 755
put payload/etc/sshd_config /data/openssh/etc/sshd_config 600
put scripts/start-ssh.sh /data/openssh/start-ssh.sh 755

KEY=/data/openssh/etc/ssh_host_ed25519_key
if [ ! -s "$KEY" ]; then
    /data/openssh/bin/ssh-keygen -t ed25519 -N '' -f "$KEY"
fi
chmod 600 "$KEY"

# Validate and start SSH before enabling its boot hook; keep existing sessions.
/data/openssh/start-ssh.sh
put scripts/post_init.sh "$HOOK" 755
sync
echo "Deployment complete. Configuration backups: $BACKUP"
echo 'Connect to port 2223 as root with an empty password; SFTP is enabled.'
echo 'Existing SSH sessions/listeners were not restarted. Reboot manually to verify startup.'
