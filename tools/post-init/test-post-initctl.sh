#!/bin/sh
set -eu
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
TMP=${TMPDIR:-/tmp}/post-initctl-test-$$
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/scripts" "$TMP/base"
export GW2_POST_INIT_BASE="$TMP/base"
export GW2_POST_INIT_HOOK="$TMP/scripts/post_init.sh"
export GW2_POST_INIT_LOCK="$TMP/lock"
CTL="$HERE/post-initctl.sh"
BODY="$TMP/body.sh"
printf '# test module\n(true) &\n' > "$BODY"
"$CTL" ensure
"$CTL" add openssh "$BODY"
"$CTL" add tun "$BODY"
[ "$(grep -c '^# BEGIN MI-GW2 POST-INIT MODULE: openssh$' "$GW2_POST_INIT_HOOK")" -eq 1 ]
[ "$(grep -c '^# BEGIN MI-GW2 POST-INIT MODULE: tun$' "$GW2_POST_INIT_HOOK")" -eq 1 ]
[ "$(grep -c '^# BEGIN MI-GW2 POST-INIT STOCK ANCHOR$' "$GW2_POST_INIT_HOOK")" -eq 1 ]
"$CTL" remove openssh
! grep -q 'MI-GW2 POST-INIT MODULE: openssh' "$GW2_POST_INIT_HOOK"
grep -q 'MI-GW2 POST-INIT MODULE: tun' "$GW2_POST_INIT_HOOK"
"$CTL" add openssh "$BODY"
"$CTL" add openssh "$BODY"
[ "$(grep -c '^# BEGIN MI-GW2 POST-INIT MODULE: openssh$' "$GW2_POST_INIT_HOOK")" -eq 1 ]
"$CTL" check
echo 'POST_INITCTL_ISOLATION_TEST_PASS'
