#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON=${OTBR_API_TEST_PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || { echo 'Set OTBR_API_TEST_PYTHON to your existing aioesphomeapi environment.' >&2; exit 1; }
exec "$PYTHON" tests/gateway_noattach.py "$@"
