#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 tools/prepare_web.py --verify
cmake -S . -B build/web-native -DOTBR_HOST_BUILD_WEB=ON -DOTBR_HOST_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/web-native --target otbr-web-http-check web-queue-test ha-client-check gateway-system-test --parallel 2
echo 'Web transport check built. No server or gateway operation started.'
