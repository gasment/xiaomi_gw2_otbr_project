#!/bin/sh
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
DEFAULT_CROSS=$HERE/../../0-build-src/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
CROSS=${MG_CROSS:-$DEFAULT_CROSS}
[ -x "${CROSS}gcc" ] || { echo 'Set MG_CROSS to the ARM musl toolchain prefix.' >&2; exit 1; }
mkdir -p "$HERE/build"
"${CROSS}gcc" -Os -Wall -Wextra -Werror -static -s "-ffile-prefix-map=$HERE=." "$HERE/src/ble-cache-clock.c" -o "$HERE/build/ble-cache-clock"
python3 "$HERE/package.py" "$@"
