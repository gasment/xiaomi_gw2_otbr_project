#!/bin/sh
set -eu
cd "$(dirname "$0")"
cmake -S . -B build/proxy-native -DOTBR_HOST_BUILD_API=ON -DOTBR_HOST_BUILD_WEB=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/proxy-native --target thread-proxy-api-check thread-proxy-protocol-test --parallel 2
./build/proxy-native/thread-proxy-protocol-test
echo 'Proxy protocol test binaries built; no Thread socket or gateway operation.'
