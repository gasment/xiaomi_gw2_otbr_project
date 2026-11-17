#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
CROSS=$BASE/../../toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
gcc -std=c99 -O2 -Wall -Wextra -Werror "$BASE/spinel-probe.c" -o "$BASE/spinel-probe-host"
python3 "$BASE/test-spinel-probe.py"
"${CROSS}gcc" -std=c99 -static -Os -Wall -Wextra -Werror -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard "$BASE/spinel-probe.c" -o "$BASE/spinel-probe"
"${CROSS}strip" "$BASE/spinel-probe"
file "$BASE/spinel-probe"
sha256sum "$BASE/spinel-probe"
echo 'Upload spinel-probe to gateway /tmp; keep original Zigbee services paused.'
