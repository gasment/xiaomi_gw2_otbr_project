#!/bin/sh
set -eu
sh /data/otbr/stop.sh
exec sh /data/otbr/start.sh
