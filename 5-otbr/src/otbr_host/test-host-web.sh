#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=${OTBR_TEST_PYTHON:-python3}
exec "$PYTHON" tests/gateway_web.py
