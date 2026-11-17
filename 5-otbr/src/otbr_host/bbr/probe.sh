#!/bin/sh
set -eu
cd "$(dirname "$0")"
sha256sum -c SHA256SUMS
echo '=== Kernel and interfaces ==='
uname -r
for F in /proc/net/ip6_mr_vif /proc/net/ip6_mr_cache; do
    if [ -r "$F" ]; then echo "PRESENT: $F"; else echo "ABSENT: $F"; fi
done
echo '=== Read-only multicast API query ==='
if ./bbr-kernel-probe; then RESULT=0; else RESULT=$?; fi
echo '=== No MRT6_INIT, interface operation, sysctl change, service restart or packet send performed ==='
exit "$RESULT"
