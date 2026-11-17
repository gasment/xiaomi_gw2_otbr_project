#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
LAB=$ROOT/tun_lab
CROSS=$ROOT/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
"${CROSS}gcc" -static -Os -Wall -Wextra -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard "$LAB/tun-smoke.c" -o "$LAB/tun-smoke"
"${CROSS}strip" "$LAB/tun-smoke"
file "$LAB/tun-smoke"
sha256sum "$LAB/tun-smoke"
echo 'Upload tun-smoke to /tmp on the gateway, then run it manually.'
