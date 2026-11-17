#!/bin/sh
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
MODE=${1:-arm}
for TOOL in cmake git python3 pkg-config; do
    command -v "$TOOL" >/dev/null 2>&1 || { echo "Missing WSL tool: $TOOL" >&2; exit 1; }
done
python3 tools/prepare_core.py --verify
mkdir -p "$ROOT/build/pkgconfig-empty"
# Do not discover and accidentally link x86_64 systemd/DBus packages into ARM.
export PKG_CONFIG_PATH=
export PKG_CONFIG_LIBDIR=$ROOT/build/pkgconfig-empty
case "$MODE" in
    arm)
        BUILD=$ROOT/build/core-arm
        cmake -S core -B "$BUILD" -DCMAKE_TOOLCHAIN_FILE="$ROOT/cmake/armv7-musl.cmake" -DMI_OTBR_STATIC=ON -DCMAKE_BUILD_TYPE=Release
        ;;
    native)
        BUILD=$ROOT/build/core-native
        cmake -S core -B "$BUILD" -DMI_OTBR_STATIC=OFF -DCMAKE_BUILD_TYPE=Release
        ;;
    *) echo 'Usage: sh build-core.sh [arm|native]' >&2; exit 2 ;;
esac
cmake --build "$BUILD" --target otbr-agent ot-ctl --parallel 2
python3 tools/check_core_build.py "$BUILD" "$MODE"
echo 'Baseline core built. No gateway upload, radio operation or Thread network configuration performed.'
