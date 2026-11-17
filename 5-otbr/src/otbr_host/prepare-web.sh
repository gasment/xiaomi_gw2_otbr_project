#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 tools/prepare_web.py
