#!/bin/sh
# Interactive only: never accept a password via argv, environment or a file.
set -eu
CONFIG=/data/openssh/etc/sshd_config
SSHD=/data/openssh/sbin/sshd
PIDFILE=/var/run/openssh-test.pid
AUTH=/res/passwd
LOCK=/tmp/mi-gw2-root-password.lock
fail() { echo "ERROR: $*" >&2; exit 1; }
auth_kind() {
    awk -F: '$1=="root" {if ($2=="") print "empty"; else if ($2 ~ /^\$6\$/) print "sha512"; else if ($2=="x") print "shadow"; else if ($2 ~ /^[!*]/) print "locked"; else print "other-hash"}' "$AUTH"
}
[ "$(id -u)" = 0 ] || fail 'Run as root.'
[ -r "$AUTH" ] || fail 'Persistent /res/passwd is missing.'
case "${1:-}" in
    --check)
        printf 'ROOT_AUTH=%s\n' "$(auth_kind)"
        grep -E '^(Port|PermitRootLogin|PasswordAuthentication|PermitEmptyPasswords)[[:space:]]' "$CONFIG"
        echo 'Read-only check; no password hash or plaintext was printed.'
        exit 0 ;;
    '') ;;
    *) echo 'Usage: sh set-root-password.sh [--check]' >&2; exit 1 ;;
esac
for tool in passwd busybox awk grep cp mv chmod rm mkdir rmdir readlink kill sync; do
    command -v "$tool" >/dev/null 2>&1 || fail "Missing tool: $tool"
done
[ -t 0 ] || fail 'Use an interactive SSH/Telnet terminal; password input is not accepted from a pipe.'
[ "$(readlink /etc/passwd)" = /res/passwd ] || fail 'Unexpected passwd layout; this script requires the validated gateway layout.'
[ ! -e /etc/shadow ] || fail 'Unexpected shadow layout; review it manually before changing credentials.'
[ -w "$AUTH" ] && [ -x "$SSHD" ] && [ -r "$CONFIG" ] || fail 'Persistent passwd or OpenSSH is not ready.'
if awk 'tolower($1) ~ /^(match|include|authenticationmethods)$/ {found=1} END {exit !found}' "$CONFIG"; then
    fail 'Custom Match/Include/AuthenticationMethods found; merge authentication settings manually.'
fi
PID=$(cat "$PIDFILE")
case "$PID" in ''|*[!0-9]*) fail 'Invalid SSH listener PID';; esac
[ "$(readlink "/proc/$PID/exe")" = "$SSHD" ] || fail 'SSH listener PID does not match the expected server.'
kill -0 "$PID" || fail 'SSH listener is not running.'
CAPABILITY=$(printf '%s\n' 'GW2-capability-test-only' | busybox cryptpw -m sha512 -P 0) || fail 'Cannot verify SHA-512 support; password unchanged.'
case "$CAPABILITY" in '$6$'*) ;; *) fail 'SHA-512 hashing is unavailable; password unchanged.';; esac
unset CAPABILITY
mkdir "$LOCK" 2>/dev/null || fail 'Another password update may be active.'
TEMP=$CONFIG.password-new-$$
cleanup() { rm -f "$TEMP"; rmdir "$LOCK" 2>/dev/null || :; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
umask 077
awk 'BEGIN {print "PermitRootLogin yes"; print "PasswordAuthentication yes"; print "PermitEmptyPasswords no"} tolower($1) !~ /^(permitrootlogin|passwordauthentication|permitemptypasswords)$/ {print}' "$CONFIG" > "$TEMP"
chmod 600 "$TEMP"
"$SSHD" -t -f "$TEMP" || fail 'Proposed SSH configuration failed validation; password unchanged.'
echo 'Install and enable the HA password patch before continuing.'
echo 'Enter the same root password configured in HA secrets.yaml. Keep this terminal open for verification.'
passwd -a sha512 root || fail 'Password update did not complete; SSH configuration was not replaced.'
[ "$(auth_kind)" = sha512 ] || fail 'SHA-512 password storage not confirmed; inspect passwd support before continuing.'
# The only backup contains SSH options, never plaintext or password database contents.
if [ ! -e "$CONFIG.before-root-password" ]; then
    cp "$CONFIG" "$CONFIG.before-root-password"
    chmod 600 "$CONFIG.before-root-password"
fi
mv -f "$TEMP" "$CONFIG"
sync
kill -HUP "$PID" || fail 'Password is set, but SSH reload failed; retain this session and inspect the listener.'
echo 'ROOT_PASSWORD_SET: persistent SHA-512 account password; SSH empty-password login disabled.'
echo 'Telnet and SSH use the same root account password. Existing SSH sessions remain open.'
echo 'Verify a NEW SSH password login and HA reconnection before closing this terminal.'
