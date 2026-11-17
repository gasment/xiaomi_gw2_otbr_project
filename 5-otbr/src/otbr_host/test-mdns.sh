#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=${OTBR_TEST_PYTHON:-python3}
exec "$PYTHON" tests/mdns_discovery.py "${1:-GATEWAY_ADDRESS}" "${2:-6053}"
