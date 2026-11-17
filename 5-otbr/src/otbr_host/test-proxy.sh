#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=$(sh tools/check-api-python.sh)
exec "$PYTHON" tests/proxy_interop.py build/proxy-native/thread-proxy-api-check
