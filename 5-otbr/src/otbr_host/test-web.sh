#!/bin/sh
set -eu
cd "$(dirname "$0")"
./build/web-native/web-queue-test
./build/web-native/gateway-system-test
python3 tests/web_http.py
python3 tests/ha_http.py
