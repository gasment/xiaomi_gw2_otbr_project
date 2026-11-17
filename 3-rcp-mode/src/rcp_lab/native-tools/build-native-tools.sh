#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
CROSS=$BASE/../../toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
gcc -std=c99 -O2 -Wall -Wextra -Werror "$BASE/radio-flasher.c" -o "$BASE/radio-flasher-host"
python3 "$BASE/test-native-flasher.py"
"${CROSS}gcc" -std=c99 -static -Os -Wall -Wextra -Werror -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard "$BASE/radio-flasher.c" -o "$BASE/rcp-native/radio-flasher"
"${CROSS}strip" "$BASE/rcp-native/radio-flasher"
file "$BASE/rcp-native/radio-flasher"
cp "$BASE/README.md" "$BASE/rcp-native/README.md"
(cd "$BASE/rcp-native" && sha256sum radio-flasher *.sh firmware/*.gbl README.md > SHA256SUMS)
tar -chzf "$BASE/rcp-native.tar.gz" -C "$BASE" rcp-native
echo 'Native gateway package ready. No gateway or radio was accessed.'
