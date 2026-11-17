#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$#" -eq 1 ] || { echo 'Gateway runtime: sh /data/otbr/check.sh. This developer helper requires an explicit file path.' >&2; exit 2; }
CHECKER=${OTBR_CONFIG_CHECK_BIN:-./build/native/otbr-config-check}
[ -x "$CHECKER" ] || { echo 'Build config tools first: sh build-checks.sh native' >&2; exit 1; }
exec "$CHECKER" "$1"
