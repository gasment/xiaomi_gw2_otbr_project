#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LAB=$ROOT/tun_lab
TREE=$LAB/kernel-work
CROSS=$ROOT/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
[ -f "$LAB/probe-report.txt" ] || { echo 'Run build-probe.sh first.' >&2; exit 1; }
if [ ! -f "$LAB/probe-report.baseline.txt" ]; then cp "$LAB/probe-report.txt" "$LAB/probe-report.baseline.txt"; fi
if [ ! -f "$TREE/.config.before-network-profile" ]; then cp "$TREE/.config" "$TREE/.config.before-network-profile"; fi
python3 "$LAB/prepare-bsp-host.py"
if [ ! -f "$TREE/.config.before-pm-profile" ]; then cp "$TREE/.config" "$TREE/.config.before-pm-profile"; fi
if [ -f "$LAB/network-layout-report.txt" ] && [ ! -f "$LAB/network-layout-report.before-pm.txt" ]; then cp "$LAB/network-layout-report.txt" "$LAB/network-layout-report.before-pm.txt"; fi
# Candidate profile based on the running gateway, not its exact recovered config.
sh "$TREE/scripts/config" --file "$TREE/.config" --enable PM --enable SUSPEND --enable NET_CORE --enable IPV6 --enable NETFILTER --enable NETFILTER_ADVANCED --enable NF_CONNTRACK --module BRIDGE --module BRIDGE_NETFILTER --module TUN
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' olddefconfig
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' modules_prepare
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' M="$LAB/probe" modules
python3 "$LAB/check-probe.py"
python3 "$LAB/check-network-layout.py"
echo 'Network layout anchor matches. Review other layouts and symbols before building/loading TUN.'
