#!/bin/sh
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
python3 tools/prepare_api.py
case "${1:-native}" in
    native)
        BUILD=$ROOT/build/api-native
        cmake -S . -B "$BUILD" -DOTBR_HOST_BUILD_API=ON -DCMAKE_BUILD_TYPE=Release
        ;;
    arm)
        BUILD=$ROOT/build/api-arm
        cmake -S . -B "$BUILD" -DOTBR_HOST_BUILD_API=ON -DOTBR_HOST_STATIC=ON -DCMAKE_TOOLCHAIN_FILE="$ROOT/cmake/armv7-musl.cmake" -DCMAKE_BUILD_TYPE=Release
        ;;
    *) echo 'Usage: sh build-api.sh [native|arm]' >&2; exit 2 ;;
esac
cmake --build "$BUILD" --parallel 2
if [ "${1:-native}" = native ]; then
    ctest --test-dir "$BUILD" --output-on-failure
fi
echo "Protocol-only Native API check server: $BUILD/otbr-native-api-check"
echo 'No server was started and no gateway operation was performed.'
