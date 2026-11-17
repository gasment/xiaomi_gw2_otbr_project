#!/bin/sh
set -eu
BASE=/tmp/rcp-native
(cd "$BASE" && sha256sum -c SHA256SUMS)
sh "$BASE/enter-bootloader.sh"
exec "$BASE/radio-flasher" flash /dev/ttyS1 "$BASE/firmware/lumi-gateway-mgl001_opentread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_460800.gbl"
