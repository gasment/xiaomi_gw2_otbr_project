#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
source_dir=$PWD
resources=$(realpath -- "${RCP_BUILD_RESOURCES:-../../../test_version_rcp/rcp-2.5.3-uart115200}")
container=$(realpath -- "${RCP_BUILDER_ROOTFS:-$resources/../builder-rootfs}")
builder=silabs-firmware-builder-20250627
sdk=simplicity_sdk_2024.6.3
toolchain=arm-gnu-toolchain-12.2.rel1-x86_64-arm-none-eabi
commit=6241e332f9e1c28e7458ee9fce80b29bcb4a3705
out="$source_dir/../build-output/firmware"
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
git clone -q --local --no-checkout -- "$resources/$builder" "$scratch/$builder"
git -C "$scratch/$builder" checkout -q --detach "$commit"
git -C "$scratch/$builder" apply "$source_dir/slc-tool-paths.patch"
cp -a --reflink=auto "$resources/$sdk" "$scratch/$sdk"
if [[ ! -e "$scratch/$sdk/extension" ]]; then
    ln -s "../$builder/gecko_sdk_extensions" "$scratch/$sdk/extension"
fi
cp "$source_dir/mgl001_openthread_rcp.yaml" "$scratch/$builder/manifests/xiaomi/"
mkdir -p "$scratch/host-tools" "$scratch/outputs" "$scratch/$toolchain" "$scratch/commander-cli"
cp /usr/bin/make "$scratch/host-tools/make.real"
cat > "$scratch/host-tools/make" <<'MAKE'
#!/bin/sh
PATH=/opt/venv/bin:$PATH exec /repo/host-tools/make.real "$@"
MAKE
cat > "$scratch/host-tools/commander" <<'COMMANDER'
#!/bin/sh
LD_LIBRARY_PATH=/repo/commander-cli/lib exec /repo/commander-cli/commander-cli "$@"
COMMANDER
chmod 755 "$scratch/host-tools/make" "$scratch/host-tools/commander"
bwrap --ro-bind "$container" / --bind "$scratch" /repo --dev /dev --proc /proc \
    --ro-bind "$resources/$toolchain" "/repo/$toolchain" \
    --ro-bind "$resources/commander-cli" /repo/commander-cli \
    --tmpfs /tmp --tmpfs /root --chdir "/repo/$builder" \
    --setenv HOME /root --setenv PATH /repo/host-tools:/opt/silabs/bin:/opt/silabs/python/bin:/usr/bin:/bin \
    --setenv LANG C.UTF-8 --setenv STUDIO_ADAPTER_PACK_PATH /opt/silabs/zap \
    /bin/bash -ec '
        git config --global --add safe.directory "$PWD"
        slc signature trust --sdk "$1"
        for extension in "$1"/extension/*/; do
            [ ! -d "$extension" ] || slc signature trust --sdk "$1" --extension-path "$extension"
        done
        exec /opt/venv/bin/python tools/build_project.py \
            --sdk "$1" --toolchain "$2" --manifest manifests/xiaomi/mgl001_openthread_rcp.yaml \
            --build-dir /repo/generated --build-system makefile --output-dir /repo/outputs \
            --no-clean-build-dir --output gbl --output out
    ' bash "/repo/$sdk" "/repo/$toolchain"
settings="$scratch/generated/config/sl_uartdrv_usart_vcom_config.h"
grep -Eq '^#define SL_UARTDRV_USART_VCOM_BAUDRATE[[:space:]]+115200$' "$settings"
grep -Eq '^#define SL_UARTDRV_USART_VCOM_PARITY[[:space:]]+usartNoParity$' "$settings"
grep -Eq '^#define SL_UARTDRV_USART_VCOM_STOP_BITS[[:space:]]+usartStopbits1$' "$settings"
grep -Eq '^#define SL_UARTDRV_USART_VCOM_FLOW_CONTROL_TYPE[[:space:]]+uartdrvFlowControlNone$' "$settings"
firmware=("$scratch"/outputs/*.gbl)
[[ "${#firmware[@]}" -eq 1 ]]
python3 "$source_dir/verify-gbl.py" "${firmware[0]}"
mkdir -p "$out"
name=lumi-gateway-mgl001_openthread_rcp_2.5.3.0_115200.gbl
install -m 644 "${firmware[0]}" "$out/$name"
(cd "$out" && sha256sum "$name" > SHA256SUMS)
