#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$#" -eq 1 ] || { echo 'Usage: sh test-gateway-entities.sh GATEWAY_ADDRESS' >&2; exit 2; }
exec "${OTBR_TEST_PYTHON:-python3}" tests/gateway_entities.py "$1"
