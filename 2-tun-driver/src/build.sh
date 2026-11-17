#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")" && pwd)
LAB=$ROOT/tun_lab
CROSS=$ROOT/toolchains/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
[ -x "${CROSS}gcc" ] || { echo 'Copy the kernel compiler first'; exit 1; }
python3 "$LAB/prepare-tree.py"
python3 "$LAB/prepare-bsp-host.py"
cp "$LAB/tested-kernel.config" "$LAB/kernel-work/.config"
make -C "$LAB/kernel-work" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' olddefconfig
make -C "$LAB/kernel-work" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' modules_prepare
make -C "$LAB/kernel-work" ARCH=arm CROSS_COMPILE="$CROSS" HOSTCFLAGS='-O2 -fcommon -std=gnu89' M="$LAB/probe" modules
python3 "$LAB/check-probe.py"
python3 "$LAB/check-network-layout.py"
sh "$LAB/build-tun.sh"
sh "$LAB/build-tun-smoke.sh"
python3 "$ROOT/package.py"
