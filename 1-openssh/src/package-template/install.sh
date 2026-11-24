#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$BASE"
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run this installer as root on the gateway.'
[ -x /bin/fw_manager.sh ] || fail 'Xiaomi stock service launcher not found.'
command -v agetprop >/dev/null 2>&1 || fail 'Not a supported Xiaomi stock system.'
agetprop | grep -Eq '\[ro.sys.model\]: \[lumi.gateway.(mcn001|mgl001)\]' || fail 'Unsupported gateway model.'
for TOOL in awk cat cmp date grep kill mkdir mv rmdir sed sh sync; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "Missing command: $TOOL"
done
echo 'Checking deployment files...'
sha256sum -c SHA256SUMS || fail 'File verification failed.'
sh -n scripts/start-ssh.sh
sh -n post-init/post-initctl.sh
sh -n post-init/install-common.sh
sh -n post-init/migrate-legacy.sh

HOOK=/data/scripts/post_init.sh

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

# Establish the safe shared entry and register only the OpenSSH module.
sh "$BASE/post-init/install-common.sh"
/data/mi-gw2-post-init/post-initctl.sh add openssh /data/mi-gw2-post-init/modules/openssh.sh
# Start or retain SSH after the stock fallback entry is already safe.
/data/openssh/start-ssh.sh
put VERSION /data/openssh/VERSION 644
sync
echo "Deployment complete. Configuration backups: $BACKUP"
echo 'Connect to port 2223 as root with an empty password; SFTP is enabled.'
echo 'Existing SSH sessions/listeners were not restarted. Reboot manually to verify startup.'
