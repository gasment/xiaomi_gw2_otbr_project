#!/bin/sh
set -eu
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
SRC=$ROOT/0-build-src/openssl/source
WORK=$ROOT/0-build-src/openssl/build-arm
DEST=$ROOT/0-build-src/openssl/arm
CROSS=$ROOT/0-build-src/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
COMMIT=84dda7853c130429210b37bee9e5b62366ca8bce
for TOOL in git perl make tar python3; do command -v "$TOOL" >/dev/null 2>&1 || { echo "Missing tool: $TOOL" >&2; exit 1; }; done
[ -x "${CROSS}gcc" ] || { echo 'Restore the ARMv7 musl toolchain first.' >&2; exit 1; }
[ "$(git -C "$SRC" rev-parse HEAD)" = "$COMMIT" ] || { echo 'OpenSSL source commit differs.' >&2; exit 1; }
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] || { echo 'OpenSSL tracked source has local edits.' >&2; exit 1; }
[ ! -e "$WORK" ] || { echo 'Build directory already exists; inspect it before a new build.' >&2; exit 1; }
[ ! -e "$DEST" ] || { echo 'OpenSSL install directory already exists; it will not be overwritten.' >&2; exit 1; }
mkdir -p "$WORK/source" "$WORK/build"
# Export tracked source only, avoiding old in-tree configuration/build files.
git -C "$SRC" archive --format=tar --output="$WORK/source.tar" "$COMMIT"
tar -xf "$WORK/source.tar" -C "$WORK/source"
rm -f "$WORK/source.tar"
cd "$WORK/build"
unset CC CXX AR RANLIB CFLAGS CPPFLAGS LDFLAGS CROSS_COMPILE
perl ../source/Configure linux-armv4 --cross-compile-prefix="$CROSS" --prefix="$DEST" --openssldir=/data/openssh/ssl --libdir=lib no-shared no-tests no-module no-dso -Os -fPIC -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard
make -j"${JOBS:-2}"
make install_sw
cp "$WORK/source/LICENSE.txt" "$DEST/LICENSE.txt"
python3 "$ROOT/tools/record-openssl-build.py" --capture
echo 'OPENSSL_STATIC_BUILD_READY: inspect the validation result, then explicitly record the new dependency hashes.'
echo 'Next: python3 tools/record-openssl-build.py --accept'
