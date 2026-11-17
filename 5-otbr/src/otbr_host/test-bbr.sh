#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=${OTBR_TEST_PYTHON:-python3}
exec "$PYTHON" tests/bbr_runtime.py "${1:-GATEWAY_ADDRESS}"
