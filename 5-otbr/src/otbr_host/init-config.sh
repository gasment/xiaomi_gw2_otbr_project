#!/bin/sh
echo 'Runtime YAML belongs on the gateway: /data/otbr/config.yaml and secrets.yaml.' >&2
echo 'The gateway installer creates missing files and preserves existing user configuration.' >&2
exit 2
