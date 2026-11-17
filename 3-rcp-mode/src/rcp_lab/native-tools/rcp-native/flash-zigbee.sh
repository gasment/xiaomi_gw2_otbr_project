#!/bin/sh
set -eu
BASE=/tmp/rcp-native
(cd "$BASE" && sha256sum -c SHA256SUMS)
sh "$BASE/enter-bootloader.sh"
exec "$BASE/radio-flasher" flash /dev/ttyS1 "$BASE/firmware/xiaomi_stock_ncp_6.6.6.0_build218.gbl"
