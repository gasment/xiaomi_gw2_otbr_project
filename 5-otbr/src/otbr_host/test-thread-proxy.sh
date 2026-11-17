#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$#" -eq 1 ] || { echo 'Usage: sh test-thread-proxy.sh GATEWAY_ADDRESS' >&2; exit 2; }
exec "${OTBR_TEST_PYTHON:-python3}" tests/proxy_deployed.py "$1"
