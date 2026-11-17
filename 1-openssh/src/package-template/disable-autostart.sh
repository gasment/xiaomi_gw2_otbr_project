#!/bin/sh
set -eu
HOOK=/data/scripts/post_init.sh
if [ -f "$HOOK" ] && grep -q 'MI_GATEWAY2_OPENSSH_DEPLOY_V1' "$HOOK"; then
    chmod 644 "$HOOK"
    sync
    echo 'SSH autostart disabled. Existing SSH sessions remain active.'
    echo 'The stock service launcher will be used on the next boot.'
else
    echo 'No boot hook managed by this deployment package was found.' >&2
    exit 1
fi
