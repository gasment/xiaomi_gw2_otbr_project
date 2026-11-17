#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec "${OTBR_TEST_PYTHON:-python3}" tests/srp_mdns.py "$@"
