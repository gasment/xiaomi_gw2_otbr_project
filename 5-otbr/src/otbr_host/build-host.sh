#!/bin/sh
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
python3 tools/prepare_core.py --verify
python3 tools/prepare_api.py
python3 tools/prepare_web.py --verify
mkdir -p "$ROOT/build/pkgconfig-empty"
export PKG_CONFIG_PATH=
export PKG_CONFIG_LIBDIR=$ROOT/build/pkgconfig-empty
PROFILE=${OTBR_HOST_PROFILE:-stable}
case "$PROFILE" in
  stable) BUILD_TAG=host; USERSPACE_MROUTE=OFF ;;
  bbr) BUILD_TAG=host-bbr; USERSPACE_MROUTE=ON ;;
  *) echo 'OTBR_HOST_PROFILE must be stable or bbr' >&2; exit 2 ;;
esac
case "${1:-arm}" in
  arm)
    BUILD=$ROOT/build/$BUILD_TAG-arm
    cmake -S . -B "$BUILD" -DOTBR_HOST_BUILD_RUNTIME=ON -DOTBR_HOST_STATIC=ON -DOTBR_HOST_KERNEL_MROUTE=OFF -DOTBR_HOST_USERSPACE_MROUTE=$USERSPACE_MROUTE -DCMAKE_TOOLCHAIN_FILE="$ROOT/cmake/armv7-musl.cmake" -DCMAKE_BUILD_TYPE=Release
    ;;
  native)
    BUILD=$ROOT/build/$BUILD_TAG-native
    cmake -S . -B "$BUILD" -DOTBR_HOST_BUILD_RUNTIME=ON -DOTBR_HOST_KERNEL_MROUTE=OFF -DOTBR_HOST_USERSPACE_MROUTE=$USERSPACE_MROUTE -DCMAKE_BUILD_TYPE=Release
    ;;
  *) echo 'Usage: sh build-host.sh [arm|native]' >&2; exit 2 ;;
esac
cmake --build "$BUILD" --target mi-otbr-host otbr-config-check backbone-policy-test config-parser-test node-restart-protocol-test bbr-checksum-test system-metrics-test gateway-system-test thread-proxy-protocol-test --parallel 2
if [ "${1:-arm}" = native ]; then
  ctest --test-dir "$BUILD" --output-on-failure
else
  READELF=$ROOT/../toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-readelf
  "$READELF" -h "$BUILD/mi-otbr-host" > "$BUILD/runtime-elf-report.txt"
  grep 'Machine:' "$BUILD/runtime-elf-report.txt"
  grep -q 'Machine:.*ARM' "$BUILD/runtime-elf-report.txt" || { echo 'Unexpected machine architecture' >&2; exit 1; }
  grep -q 'Class:.*ELF32' "$BUILD/runtime-elf-report.txt" || { echo 'Unexpected ELF class' >&2; exit 1; }
  if "$READELF" -l "$BUILD/mi-otbr-host" | grep -q INTERP; then echo 'Unexpected dynamic interpreter' >&2; exit 1; fi
  if "$READELF" -d "$BUILD/mi-otbr-host" | grep -q '(NEEDED)'; then echo 'Unexpected shared dependency' >&2; exit 1; fi
fi
echo "Combined runtime: $BUILD/mi-otbr-host"
echo 'HOST_BUILD_PASS. No runtime started, gateway upload or network operation performed.'
