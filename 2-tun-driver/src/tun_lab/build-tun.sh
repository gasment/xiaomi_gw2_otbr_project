#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LAB=$ROOT/tun_lab
TREE=$LAB/kernel-work
CROSS=$ROOT/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
python3 "$LAB/check-probe.py"
python3 "$LAB/check-network-layout.py"
grep -q '^CONFIG_TUN=m$' "$TREE/.config" || { echo 'CONFIG_TUN=m is required.' >&2; exit 1; }
grep -q '^# CONFIG_MODVERSIONS is not set$' "$TREE/.config" || { echo 'Unexpected MODVERSIONS config.' >&2; exit 1; }
mkdir -p "$LAB/tun"
# Use the exact BSP source as an isolated external module, not all drivers/net.
cp "$TREE/drivers/net/tun.c" "$LAB/tun/tun.c"
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' M="$LAB/tun" modules
python3 "$LAB/check-tun.py"
echo 'TUN built and static checks passed. No module was uploaded or loaded.'
