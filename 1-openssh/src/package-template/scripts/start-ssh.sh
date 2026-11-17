#!/bin/sh
set -eu
SSHD=/data/openssh/sbin/sshd
CONFIG=/data/openssh/etc/sshd_config
PIDFILE=/var/run/openssh-test.pid
umask 022
mkdir -p /var/empty /var/run /var/log
chown 0:0 /var/empty
chmod 755 /var/empty
"$SSHD" -t -f "$CONFIG"
if [ -s "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    case "$PID" in
        ''|*[!0-9]*) ;;
        *)
            if kill -0 "$PID" 2>/dev/null; then
                EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || true)
                case "$EXE" in
                    "$SSHD"|"$SSHD (deleted)")
                        echo "OpenSSH is already running (PID $PID)."
                        exit 0
                        ;;
                esac
            fi
            ;;
    esac
fi
"$SSHD" -f "$CONFIG" -E /var/log/openssh.log
echo 'OpenSSH started on port 2223.'
