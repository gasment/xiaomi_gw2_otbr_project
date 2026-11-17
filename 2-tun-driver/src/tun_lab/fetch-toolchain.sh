#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/../../.." && pwd)
NAME=gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf
ARCHIVE=$ROOT/0-build-src/downloads/$NAME.tar.xz
TARGET=$ROOT/0-build-src/toolchains/$NAME
if [ -x "$TARGET/bin/arm-none-linux-gnueabihf-gcc" ]; then
    "$TARGET/bin/arm-none-linux-gnueabihf-gcc" --version
    echo 'Shared kernel toolchain already present. No download or build.'
    exit 0
fi
mkdir -p "$ROOT/0-build-src/downloads" "$ROOT/0-build-src/toolchains"
if [ ! -s "$ARCHIVE" ]; then
    curl -fL --retry 3 -o "$ARCHIVE.part" "https://armkeil.blob.core.windows.net/developer/Files/downloads/gnu-a/9.2-2019.12/binrel/$NAME.tar.xz"
    mv "$ARCHIVE.part" "$ARCHIVE"
fi
[ ! -e "$TARGET" ] || { echo 'Incomplete toolchain directory exists; inspect it first.' >&2; exit 1; }
tar -xJf "$ARCHIVE" -C "$ROOT/0-build-src/toolchains"
"$TARGET/bin/arm-none-linux-gnueabihf-gcc" --version
echo 'Shared kernel toolchain ready. No kernel/module build performed.'
