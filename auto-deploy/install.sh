#!/bin/sh
# Local-upload deployment. No download, package manager or host-side Python.
set -eu
BUNDLE=$(CDPATH= cd "$(dirname "$0")" && pwd)
BASE=/data/mi-gw2-auto
LOCK=/tmp/mi-gw2-auto.lock
WORK=/tmp/mi-gw2-auto-work
HOOK=/data/scripts/post_init.sh
ACTION=${1:-help}
NO_REBOOT=${2:-}
LOG=
fail() { echo "ERROR: $*" >&2; exit 1; }
log() {
    printf '%s\n' "$*"
    if [ -n "$LOG" ]; then printf '%s\n' "$*" >> "$LOG"; fi
}
usage() {
    echo 'Usage: sh install.sh check | install [--no-reboot] | resume | verify | status'
    echo 'install flashes the radio to RCP, replaces stock Zigbee operation and reboots once.'
    echo 'Upload/extract the complete local bundle first. No remote download is used.'
}
case "$ACTION" in check|install|resume|verify|status) ;; help|--help|-h) usage; exit 0;; *) usage; exit 1;; esac
case "$NO_REBOOT" in ''|--no-reboot) ;; *) fail 'Unknown option';; esac
[ -z "$NO_REBOOT" ] || [ "$ACTION" = install ] || fail '--no-reboot applies only to install'
[ "$(id -u)" = 0 ] || fail 'Run as root on the gateway.'
[ -f "$BUNDLE/VERSION" ] || fail 'Extract the complete bundle; VERSION is missing.'
VERSION=$(cat "$BUNDLE/VERSION")
case "$VERSION" in ''|*[!0-9.]*) fail 'Invalid bundle version';; esac
SSH=mi_gateway_2_openssh_deploy-$VERSION.tar.gz
TUN=mi_gateway_2_tun_deploy-$VERSION.tar.gz
NATIVE=rcp-native-$VERSION.tar.gz
MODE=rcp-mode-$VERSION.tar.gz
BLE=rcp-openmiio-$VERSION.tar.gz
HOST=mi-gw2-otbr-$VERSION.tar.gz
RECOVERY=rcp-recovery-update-$VERSION.tar.gz
PROBE=spinel-probe-$VERSION
OPENMIIO=openmiio_agent-1.2.1-arm

# VERIFY_FUNCTIONS_BEGIN
verify_file() {
    VF_DIR=$1
    VF_NAME=$2
    VF_HASH=$(awk -v n="$VF_NAME" '$2 == n {print $1}' "$BASE_MANIFEST")
    [ "${#VF_HASH}" -eq 64 ] || fail "Missing/ambiguous digest: $VF_NAME"
    case "$VF_HASH" in *[!0-9a-f]*) fail 'Invalid digest';; esac
    [ -f "$VF_DIR/$VF_NAME" ] && [ ! -L "$VF_DIR/$VF_NAME" ] || fail "Missing regular file: $VF_NAME"
    (cd "$VF_DIR" && printf '%s  %s\n' "$VF_HASH" "$VF_NAME" | sha256sum -c -) || fail "Checksum failed: $VF_NAME"
}
verify_installed() {
    VI_PREFIX=${1:-/data/}
    VI_LINES=$(awk -v p="$VI_PREFIX" 'index($2,p) == 1 {print}' "$BASE/installed-files.sha256")
    [ -n "$VI_LINES" ] || fail 'Empty installed-file expectation'
    printf '%s\n' "$VI_LINES" | sha256sum -c - || fail "Installed files differ: $VI_PREFIX"
}
# VERIFY_FUNCTIONS_END
model_check() {
    [ "$(uname -m)" = armv7l ] || fail 'Requires the validated ARMv7 gateway.'
    [ -x /bin/fw_manager.sh ] || fail 'Stock Xiaomi launcher is missing.'
    agetprop | grep -Eq '\[ro.sys.model\]: \[lumi.gateway.(mcn001|mgl001)\]' || fail 'Unsupported model.'
    [ "$(uname -r)" = 4.9.84 ] || fail 'Unsupported kernel release.'
}
check_tools() {
    for TOOL in sha256sum tar awk cat cmp cp mv chmod mkdir rmdir rm tr grep df uname id sync sleep kill killall pidof ps fuser mount umount insmod mknod chown date readlink sed usleep cut wc touch reboot agetprop tail timeout; do
        command -v "$TOOL" >/dev/null 2>&1 || fail "Missing gateway command: $TOOL"
    done
    timeout --help 2>&1 | grep -q '\-t SECS' || fail 'Expected BusyBox timeout syntax is missing.'
}
free_space() {
    FS_FREE=$(df -Pk "$1" | awk 'END {print $4}')
    case "$FS_FREE" in ''|*[!0-9]*) fail "Cannot read free space: $1";; esac
    [ "$FS_FREE" -ge "$2" ] || fail "Insufficient free space on $1; need $2 KiB."
}
verify_bundle() {
    BASE_MANIFEST=$BUNDLE/SHA256SUMS
    [ -f "$BASE_MANIFEST" ] || fail 'Bundle checksum manifest is missing.'
    for F in VERSION install.sh README.md installed-files.sha256 assets/$SSH assets/$TUN assets/$NATIVE assets/$MODE assets/$BLE assets/$HOST assets/$RECOVERY assets/$PROBE assets/$OPENMIIO; do
        verify_file "$BUNDLE" "$F"
    done
}
# RELEASE_DOWNLOAD_ARCHIVE_BEGIN
release_download_archive() {
    # Call only after verify_bundle: the expanded files have all passed SHA256.
    # The PC transfer archive is now redundant; keep the verified expanded bundle.
    [ "$BUNDLE" = /tmp/mi-gw2-auto-deploy ] || return 0
    RD_ARCHIVE=/tmp/mi-gw2-pc-deploy/mi-gw2-auto-deploy-$VERSION.tar.gz
    if [ -f "$RD_ARCHIVE" ] && [ ! -L "$RD_ARCHIVE" ]; then
        rm -f "$RD_ARCHIVE" || fail 'Cannot release the verified transfer archive.'
        echo 'TRANSFER_ARCHIVE_RELEASED: expanded bundle verified; /tmp space reclaimed.'
    fi
}
# RELEASE_DOWNLOAD_ARCHIVE_END
state() { cat "$BASE/stage" 2>/dev/null || echo new; }
# JOURNAL_FUNCTIONS_BEGIN
write_state() {
    printf '%s\n' "$1" > "$BASE/stage.new"
    mv -f "$BASE/stage.new" "$BASE/stage"
    sync
    log "DEPLOY_STAGE=$1"
}
validate_stage() {
    case "$1" in new|ssh|tun|radio-in-progress|waiting-reboot|ble|host|complete) ;; *) fail 'Unknown deployment journal state';; esac
}
fresh_install_check() {
    for F in /data/openssh /data/tun /data/rcp-mode /data/rcp-openmiio /data/otbr; do
        [ ! -e "$F" ] || fail "Existing component $F; use its documented upgrade path. No automatic reflash."
    done
    if [ -e "$HOOK" ]; then fail 'A custom boot hook already exists; use manual installation.'; fi
    [ ! -d /tmp/rcp-native ] || fail 'An existing native flash session is present; inspect it first.'
}
# JOURNAL_FUNCTIONS_END
extract() {
    verify_file "$ASSETS_PARENT" "assets/$1"
    mkdir -p "$WORK"
    tar -xzf "$ASSETS_PARENT/assets/$1" -C "$WORK"
    (cd "$WORK/$2" && sha256sum -c SHA256SUMS) || fail "Inner package checksum failed: $1"
    [ "$(cat "$WORK/$2/VERSION")" = "$VERSION" ] || fail 'Inner package version differs.'
}
# PLATFORM_PREFLIGHT_BEGIN
platform_preflight() {
    extract "$TUN" mi_gateway_2_tun_deploy
    ACTUAL_KERNEL=$(cat /proc/version)
    EXPECTED_KERNEL=$(cat "$WORK/mi_gateway_2_tun_deploy/payload/expected-proc-version.txt")
    if [ "$ACTUAL_KERNEL" != "$EXPECTED_KERNEL" ]; then
        echo 'UNSUPPORTED_KERNEL_BASELINE' >&2
        echo "Gateway firmware: $(agetprop ro.sys.mi_fw_ver)_$(agetprop ro.sys.mi_build_num)" >&2
        echo 'Validated package baseline: stock 1.0.8_0015; exact kernel build required.' >&2
        printf 'Actual kernel: %s\nExpected kernel: %s\n' "$ACTUAL_KERNEL" "$EXPECTED_KERNEL" >&2
        fail 'Kernel build does not match this release. No module load or radio write was requested. Use a matching stock build or a separately validated package.'
    fi
    extract "$MODE" rcp-mode
    (cd "$WORK/rcp-mode" && sha256sum -c payload/stock.sha256) || fail 'Stock launchers differ from the validated package; no component installer was run.'
    echo 'PLATFORM_BASELINE_PASS: exact kernel build and stock launchers match.'
}
# PLATFORM_PREFLIGHT_END
run_installer() {
    log "Installing $1"
    if sh "$WORK/$1/install.sh" > "$BASE/last-step.log" 2>&1; then
        cat "$BASE/last-step.log"
    else
        cat "$BASE/last-step.log"
        fail "Installer failed: $1; see $BASE/last-step.log. No subsequent step was run."
    fi
}
probe_rcp() {
    verify_file "$ASSETS_PARENT" "assets/$PROBE"
    chmod 700 "$ASSETS_PARENT/assets/$PROBE"
    "$ASSETS_PARENT/assets/$PROBE" > "$BASE/rcp-probe.log" 2>&1 || { cat "$BASE/rcp-probe.log"; fail 'Running RCP probe failed.'; }
    grep -q SPINEL_RCP_PROBE_PASS "$BASE/rcp-probe.log" || fail 'RCP response was not verified.'
    cat "$BASE/rcp-probe.log"
}
save_resume_assets() {
    mkdir -p "$BASE/cache/assets"
    for F in "$BLE" "$HOST" "$PROBE"; do
        verify_file "$ASSETS_PARENT" "assets/$F"
        cp "$ASSETS_PARENT/assets/$F" "$BASE/cache/assets/$F.new"
        mv -f "$BASE/cache/assets/$F.new" "$BASE/cache/assets/$F"
    done
    # Keep the persisted cache private; the next boot verifies every cached file.
    chmod 700 "$BASE/cache" "$BASE/cache/assets"
    printf '%s\n' "$(cat /proc/sys/kernel/random/boot_id)" > "$BASE/install-boot-id"
}
write_resume_hook() {
    cmp -s "$HOOK" /data/rcp-mode/post_init.sh || fail 'Expected RCP boot hook is not active.'
    cat > "$BASE/resume-post_init.sh" <<'BOOT_HOOK'
#!/bin/sh
# MI_GW2_AUTO_DEPLOY_RESUME_V1
set -u
BASE=/data/mi-gw2-auto
HOOK=/data/scripts/post_init.sh
if ! cmp -s "$HOOK" "$BASE/resume-post_init.sh"; then exit 1; fi
# Restore the ordinary RCP chain before running it; never stack resume wrappers.
if ! (cd /data/rcp-mode && sha256sum -c payload.sha256); then exit 1; fi
cp /data/rcp-mode/post_init.sh "$HOOK.new" || exit 1
chmod 755 "$HOOK.new" || exit 1
mv -f "$HOOK.new" "$HOOK" || exit 1
sh /data/rcp-mode/post_init.sh
RC=$?
if [ "$RC" -eq 0 ]; then
    sh "$BASE/install.sh" resume </dev/null >> "$BASE/resume.log" 2>&1 &
fi
exit "$RC"
BOOT_HOOK
    chmod 700 "$BASE/resume-post_init.sh"
    cp "$BASE/resume-post_init.sh" "$HOOK.new"
    chmod 755 "$HOOK.new"
    mv -f "$HOOK.new" "$HOOK"
    sync
}
verify_final() {
    verify_installed
    [ -f /data/otbr/boot-wrapper.sha256 ] || fail 'Host boot-wrapper expectation is missing.'
    sha256sum -c /data/otbr/boot-wrapper.sha256 || fail 'Final boot hook differs.'
    grep -q '^tun ' /proc/modules || fail 'TUN module is not loaded.'
    [ "$(cat /sys/class/misc/tun/dev)" = 10:200 ] && [ -c /dev/net/tun ] || fail 'TUN device is not ready.'
    if sh /data/otbr/check.sh > "$BASE/config-check.log" 2>&1; then
        log 'DEPLOY_FILES_VERIFIED_CONFIG_VALID: configuration parses; actual Thread attachment must be checked separately.'
    else
        log 'DEPLOY_FILES_VERIFIED_CONFIG_REQUIRED: edit /data/otbr/config.yaml and secrets.yaml on the gateway.'
        log 'Then run: sh /data/otbr/check.sh; sh /data/otbr/restart.sh'
    fi
}
if [ "$ACTION" = status ]; then
    echo "VERSION=$VERSION STAGE=$(state)"
    [ ! -f "$BASE/deploy.log" ] || tail -n 20 "$BASE/deploy.log"
    exit 0
fi
check_tools
model_check
if [ "$ACTION" = check ]; then
    verify_bundle
    release_download_archive
    free_space /data 40000
    free_space /tmp 28000
    ASSETS_PARENT=$BUNDLE
    platform_preflight
    echo 'CHECK_ONLY_PASS: local bundle, model, kernel release, tools and capacity checked. No install, UART or flash operation.'
    echo 'No component installer was run; exact kernel and stock launchers already matched.'
    exit 0
fi
if ! mkdir "$LOCK" 2>/dev/null; then fail 'Deployment lock exists; another deployment may be active. Inspect it before retrying.'; fi
printf '%s\n' "$$" > "$LOCK/pid"
cleanup() { rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || :; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
if [ "$ACTION" = verify ]; then
    [ -f "$BASE/installed-files.sha256" ] || fail 'No local deployment verification state.'
    verify_final
    exit 0
fi
if [ "$ACTION" = install ]; then
    verify_bundle
    release_download_archive
    if [ ! -f "$BASE/stage" ]; then
        fresh_install_check
        free_space /data 40000
        free_space /tmp 28000
        [ -r /proc/sys/kernel/random/boot_id ] || fail 'Kernel boot identifier is unavailable.'
        ASSETS_PARENT=$BUNDLE
        # Preflight exact TUN ABI and unmodified stock launchers before any install.
        platform_preflight
        mkdir -p "$BASE"
        chmod 700 "$BASE"
        for F in install.sh VERSION SHA256SUMS installed-files.sha256; do cp "$BUNDLE/$F" "$BASE/$F"; done
        chmod 700 "$BASE/install.sh"
        printf '%s\n' "$BUNDLE" > "$BASE/bundle-path"
        LOG=$BASE/deploy.log
        write_state new
    else
        [ "$(cat "$BASE/VERSION")" = "$VERSION" ] || fail 'Existing deployment state has another version.'
        LOG=$BASE/deploy.log
    fi
    ASSETS_PARENT=$BUNDLE
    BASE_MANIFEST=$BASE/SHA256SUMS
else
    [ -f "$BASE/stage" ] || fail 'No deployment journal to resume.'
    [ "$(cat "$BASE/VERSION")" = "$VERSION" ] || fail 'Resume version mismatch.'
    ASSETS_PARENT=$BASE/cache
    BASE_MANIFEST=$BASE/SHA256SUMS
    LOG=$BASE/deploy.log
fi
STAGE=$(state)
validate_stage "$STAGE"
case "$STAGE" in
    radio-in-progress) fail 'Radio write was interrupted or failed. Do not auto-reflash; inspect the bootloader and use the native recovery package.';;
    complete) verify_final; exit 0;;
esac
if [ "$STAGE" = new ]; then
    extract "$SSH" mi_gateway_2_openssh_deploy
    run_installer mi_gateway_2_openssh_deploy
    verify_installed /data/openssh/
    cmp -s "$HOOK" "$WORK/mi_gateway_2_openssh_deploy/scripts/post_init.sh" || fail 'SSH boot hook differs.'
    write_state ssh
    STAGE=ssh
fi
if [ "$STAGE" = ssh ]; then
    extract "$TUN" mi_gateway_2_tun_deploy
    run_installer mi_gateway_2_tun_deploy
    verify_installed /data/tun/
    /data/tun/tun-smoke > "$BASE/tun-smoke.log" 2>&1 || { cat "$BASE/tun-smoke.log"; fail 'IPv6 TUN smoke test failed.'; }
    grep -q TUN_IPV6_ROUNDTRIP_PASS "$BASE/tun-smoke.log" || fail 'Missing TUN roundtrip result.'
    write_state tun
    STAGE=tun
fi
if [ "$STAGE" = tun ]; then
    verify_installed /data/openssh/
    verify_installed /data/tun/
    verify_file "$ASSETS_PARENT" "assets/$OPENMIIO"
    if [ -e /data/openmiio_agent ]; then
        cmp -s /data/openmiio_agent "$ASSETS_PARENT/assets/$OPENMIIO" || fail 'Existing openmiio binary differs; refusing to replace it.'
    else
        cp "$ASSETS_PARENT/assets/$OPENMIIO" /data/openmiio_agent.new
        chmod 755 /data/openmiio_agent.new
        mv -f /data/openmiio_agent.new /data/openmiio_agent
    fi
    if [ -z "$(pidof openmiio_agent 2>/dev/null || :)" ]; then
        /data/openmiio_agent miio mqtt cache central </dev/null > /var/log/openmiio.log 2>&1 &
        sleep 2
    fi
    [ -n "$(pidof openmiio_agent 2>/dev/null || :)" ] || fail 'openmiio is not running.'
    [ ! -e /tmp/rcp-native ] || fail 'An existing radio session is present; no automatic overwrite.'
    verify_file "$ASSETS_PARENT" "assets/$NATIVE"
    tar -xzf "$ASSETS_PARENT/assets/$NATIVE" -C /tmp
    (cd /tmp/rcp-native && sha256sum -c SHA256SUMS)
    extract "$MODE" rcp-mode
    save_resume_assets
    write_state radio-in-progress
    sh /tmp/rcp-native/prepare-local.sh
    # Install NEXT-BOOT isolation before writing, protecting an interrupted flash.
    run_installer rcp-mode
    sh /tmp/rcp-native/probe-bootloader.sh
    sh /tmp/rcp-native/flash-rcp.sh
    sleep 2
    probe_rcp
    verify_installed /data/rcp-mode/
    write_resume_hook
    write_state waiting-reboot
    log 'RCP_VERIFIED_REBOOT_REQUIRED: continuation is installed; remaining assets are saved under /data.'
    if [ "$NO_REBOOT" = --no-reboot ]; then
        log 'Run reboot manually; deployment resumes automatically after startup.'
        exit 0
    fi
    sync
    reboot
    exit 0
fi
if [ "$STAGE" = waiting-reboot ]; then
    [ "$(cat /proc/sys/kernel/random/boot_id)" != "$(cat "$BASE/install-boot-id")" ] || fail 'A reboot is required before continuation; radio will not be flashed again.'
    # The one-shot boot wrapper normally restores this before launching resume.
    cmp -s "$HOOK" /data/rcp-mode/post_init.sh || fail 'Expected RCP boot hook is not active.'
    (cd /data/rcp-mode && sha256sum -c payload.sha256)
    cmp -s /bin/fw_manager.sh /data/rcp-mode/fw_manager.sh || fail 'RCP isolation is not active.'
    cmp -s /bin/app_monitor.sh /data/rcp-mode/app_monitor.sh || fail 'Zigbee monitor is not isolated.'
    [ -z "$(fuser /dev/ttyS1 2>&1 || :)" ] || fail 'UART has another owner.'
    probe_rcp
    extract "$BLE" rcp-openmiio
    run_installer rcp-openmiio
    sh /data/rcp-openmiio/start.sh --now
    verify_installed /data/rcp-openmiio/
    write_state ble
    STAGE=ble
fi
if [ "$STAGE" = ble ]; then
    extract "$HOST" otbr-deploy
    run_installer otbr-deploy
    write_state host
    STAGE=host
fi
if [ "$STAGE" = host ]; then
    verify_final
    write_state complete
    # Delete only this deployment's verified cache; keep journal and logs.
    [ "$ASSETS_PARENT" = "$BASE/cache" ] || fail 'Unexpected cache cleanup path.'
    for F in "$BLE" "$HOST" "$PROBE"; do rm -f "$BASE/cache/assets/$F"; done
    rmdir "$BASE/cache/assets" "$BASE/cache" 2>/dev/null || :
    log 'LOCAL_AUTO_DEPLOY_COMPLETE: files verified; inspect /data/otbr/status.sh after configuring Thread.'
fi
