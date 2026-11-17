#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
python3 "$BASE/prepare-firmware.py"
sh "$BASE/rcp_lab/native-tools/build-native-tools.sh"
sh "$BASE/rcp_lab/native-tools/build-spinel-probe.sh"
python3 "$BASE/generate-isolation.py"
python3 "$BASE/package.py"
