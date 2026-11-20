#!/bin/sh
set -u
MINIMUM=${1:-1.0.8_0015}
CURRENT=
OS_RELEASE=${GW2_OS_RELEASE:-/etc/os-release}
if [ -r "$OS_RELEASE" ]; then
    CURRENT=$(sed -n 's/^LUMI_VERSION=//p' "$OS_RELEASE" | head -n 1 | tr -d '\r')
fi
if [ -z "$CURRENT" ]; then
    CURRENT="$(agetprop ro.sys.mi_fw_ver 2>/dev/null)_$(agetprop ro.sys.mi_build_num 2>/dev/null)"
fi
[ -n "$CURRENT" ] && [ "$CURRENT" != "_" ] || {
    echo 'Unable to read LUMI_VERSION from /etc/os-release.' >&2
    exit 1
}

firmware_ge() {
    awk -v current="$1" -v minimum="$2" '
        function parse(value, out,    parts, n) {
            split(value, parts, "_")
            n=split(parts[1], out, ".")
            out[4]=(2 in parts ? parts[2] : "0")+0
            return n
        }
        BEGIN {
            na=parse(current,A)
            nb=parse(minimum,B)
            for (i=1;i<=3;i++) {
                a=(i<=na && A[i] != "" ? A[i]+0 : 0)
                b=(i<=nb && B[i] != "" ? B[i]+0 : 0)
                if (a>b) exit 0
                if (a<b) exit 1
            }
            exit !(A[4]+0 >= B[4]+0)
        }
    '
}

if ! firmware_ge "$CURRENT" "$MINIMUM"; then
    echo "LUMI_VERSION_TOO_OLD current=$CURRENT minimum=$MINIMUM" >&2
    exit 1
fi
echo "LUMI_VERSION_OK current=$CURRENT minimum=$MINIMUM"
