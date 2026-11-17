#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v cmake >/dev/null 2>&1 || { echo 'Install cmake and a build tool in WSL first.' >&2; exit 1; }
MODE=${1:-native}
case "$MODE" in
  native)
    cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
    cmake --build build/native --parallel 2
    ctest --test-dir build/native --output-on-failure
    ;;
  arm)
    cmake -S . -B build/arm -DCMAKE_TOOLCHAIN_FILE=cmake/armv7-musl.cmake -DOTBR_HOST_STATIC=ON -DCMAKE_BUILD_TYPE=Release
    cmake --build build/arm --parallel 2
    ;;
  *) echo 'Usage: sh build-checks.sh [native|arm]' >&2; exit 2 ;;
esac
