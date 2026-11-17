#!/bin/sh
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
PROBE_CROSS=$ROOT/../toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
BUILD=$ROOT/build/bbr-probe-arm
mkdir -p "$BUILD"
"${PROBE_CROSS}gcc" -O2 -Wall -Wextra -Werror -static bbr/kernel_probe.c -o "$BUILD/bbr-kernel-probe"
"${PROBE_CROSS}strip" "$BUILD/bbr-kernel-probe"
python3 tools/package_bbr_probe.py
echo 'Upload bbr-kernel-probe.tar.gz to gateway /tmp. No Host rebuild, gateway operation or BBR enable was performed.'
