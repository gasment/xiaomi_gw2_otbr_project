#!/bin/sh
set -eu
BASE=/tmp/rcp-native
(cd "$BASE" && sha256sum -c SHA256SUMS)
sh "$BASE/enter-bootloader.sh"
exec "$BASE/radio-flasher" flash /dev/ttyS1 "$BASE/firmware/lumi-gateway-mgl001_openthread_rcp_2.5.3.0_115200.gbl"
