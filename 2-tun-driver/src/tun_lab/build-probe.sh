#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LAB=$ROOT/tun_lab
TREE=$LAB/kernel-work
CROSS=$ROOT/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
[ -x "${CROSS}gcc" ] || { echo 'Run fetch-toolchain.sh first.' >&2; exit 1; }
for TOOL in make gcc python3 flex bison bc; do
    command -v "$TOOL" >/dev/null || { echo "Missing host tool: $TOOL" >&2; exit 1; }
done
python3 "$LAB/prepare-tree.py"
python3 "$LAB/prepare-bsp-host.py"
# Keep the initial SDK configuration for this first measurement.
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' olddefconfig
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' modules_prepare
make -C "$TREE" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' M="$LAB/probe" modules
python3 "$LAB/check-probe.py"
echo 'Static ABI probe finished. No module was uploaded or loaded.'
