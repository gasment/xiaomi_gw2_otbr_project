#!/bin/sh
set -eu
BASE=/tmp/rcp-native
sh "$BASE/enter-bootloader.sh"
exec "$BASE/radio-flasher" probe /dev/ttyS1
