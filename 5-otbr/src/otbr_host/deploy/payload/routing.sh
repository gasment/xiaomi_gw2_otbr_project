#!/bin/sh
set -eu
SNAPSHOT=/tmp/mi-otbr-routing.before
case "${1:-}" in
 apply)
    [ -w /proc/sys/net/ipv6/conf/all/forwarding ] || { echo 'IPv6 forwarding unavailable' >&2; exit 1; }
    umask 077
    if [ ! -f "$SNAPSHOT" ]; then
        : > "$SNAPSHOT.new"
        for F in /proc/sys/net/ipv6/conf/*/forwarding /proc/sys/net/ipv6/conf/*/accept_ra /proc/sys/net/ipv6/conf/*/disable_ipv6; do
            [ -r "$F" ] || continue
            # Some gateway proc files return a value without a terminating
            # newline. BusyBox read then returns 1, which triggers set -e.
            VALUE=$(cat "$F")
            case "$VALUE" in 0|1|2) ;; *) echo "Invalid IPv6 sysctl value: $F" >&2; exit 1;; esac
            printf '%s %s\n' "$F" "$VALUE" >> "$SNAPSHOT.new"
        done
        mv "$SNAPSHOT.new" "$SNAPSHOT"
    fi
    for F in /proc/sys/net/ipv6/conf/*/disable_ipv6; do
        [ ! -w "$F" ] || printf '0\n' > "$F"
    done
    # Forwarding must not disable IPv6 RA learning on the LAN uplinks.
    for F in /proc/sys/net/ipv6/conf/*/accept_ra; do
        case "$F" in */lo/*) continue;; esac
        [ ! -w "$F" ] || printf '2\n' > "$F"
    done
    printf '1\n' > /proc/sys/net/ipv6/conf/all/forwarding
    printf '1\n' > /proc/sys/net/ipv6/conf/default/forwarding
    ;;
 restore)
    [ -f "$SNAPSHOT" ] || exit 0
    while read F VALUE; do
        case "$F" in /proc/sys/net/ipv6/conf/*/forwarding|/proc/sys/net/ipv6/conf/*/accept_ra|/proc/sys/net/ipv6/conf/*/disable_ipv6) ;; *) exit 1;; esac
        case "$VALUE" in 0|1|2) ;; *) exit 1;; esac
        [ ! -w "$F" ] || printf '%s\n' "$VALUE" > "$F"
    done < "$SNAPSHOT"
    rm -f "$SNAPSHOT"
    ;;
 *) echo 'Usage: routing.sh apply|restore' >&2; exit 2;;
esac
