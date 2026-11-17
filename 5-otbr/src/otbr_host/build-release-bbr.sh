#!/bin/sh
set -eu
cd "$(dirname "$0")"
export OTBR_HOST_PROFILE=bbr
python3 tests/bbr_adapter.py
exec sh build-release.sh
