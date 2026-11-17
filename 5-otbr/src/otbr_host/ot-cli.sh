#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec "${OTBR_TEST_PYTHON:-python3}" tools/ot_cli.py "$@"
