#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
NAME=gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf
ARCHIVE=$ROOT/downloads/$NAME.tar.xz
TARGET=$ROOT/toolchains/$NAME
mkdir -p "$ROOT/downloads" "$ROOT/toolchains"
if [ ! -s "$ARCHIVE" ]; then
    curl -fL --retry 3 -o "$ARCHIVE.part" "https://armkeil.blob.core.windows.net/developer/Files/downloads/gnu-a/9.2-2019.12/binrel/$NAME.tar.xz"
    mv "$ARCHIVE.part" "$ARCHIVE"
fi
if [ ! -x "$TARGET/bin/arm-none-linux-gnueabihf-gcc" ]; then
    [ ! -e "$TARGET" ] || { echo 'Incomplete toolchain directory exists; inspect it first.' >&2; exit 1; }
    tar -xJf "$ARCHIVE" -C "$ROOT/toolchains"
fi
"$TARGET/bin/arm-none-linux-gnueabihf-gcc" --version
echo 'Toolchain ready. No kernel or module was built.'
