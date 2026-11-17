#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=$(sh tools/check-api-python.sh)
exec "$PYTHON" tests/api_interop.py build/api-native/otbr-native-api-check
