#!/bin/sh
set -eu
BASE=$(CDPATH= cd "$(dirname "$0")" && pwd)
CROSS=$BASE/external/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-
SSL=$BASE/external/openssl-arm
[ -x "${CROSS}gcc" ] && [ -f "$SSL/lib/libcrypto.a" ] || { echo 'Copy external dependencies first; see ../README.md'; exit 1; }
export CC=${CROSS}gcc
export AR=${CROSS}ar
export RANLIB=${CROSS}ranlib
export CFLAGS='-Os -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard -pipe -Wno-error=discarded-qualifiers -Wno-error=format-truncation'
export LDFLAGS='-static -pthread'
cd "$BASE/openssh-portable"
./configure --build=x86_64-linux-gnu --host=arm-buildroot-linux-musleabihf --prefix=/data/openssh --sysconfdir=/data/openssh/etc --libexecdir=/data/openssh/libexec --with-ssl-dir="$SSL" --with-privsep-user=sshd --with-privsep-path=/var/empty --with-sandbox=no --with-default-path=/bin:/sbin:/usr/bin:/usr/sbin --without-pie --without-zlib --without-pam --without-selinux --without-libedit --disable-pkcs11 --disable-security-key --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx
make -j2 sshd sshd-session sshd-auth ssh-keygen
"${CROSS}strip" sshd sshd-session sshd-auth ssh-keygen
python3 "$BASE/package.py"
