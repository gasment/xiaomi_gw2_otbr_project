from __future__ import annotations

import base64
import re
import shlex
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from gateway import (
    CommandResult,
    GatewayError,
    ReadOnlyFTPServer,
    TelnetSession,
    TemporaryFirewall,
    ftp_secret,
    local_ip_towards,
)
from legacy_versions import LEGACY_030, LEGACY_030_GITHUB_OTBR
from resources import COMPONENT_ASSETS, asset_catalog, asset_version, load_manifest, verify_asset, version_tuple

LogFn = Callable[[str], None]
ConfirmFn = Callable[[str, str], bool]


@dataclass
class DeployOptions:
    reboot: bool = True
    full_restore: bool = True
    flash_rcp: bool = True


@dataclass
class ComponentStatus:
    installed: str = "unknown"
    running: str = "unknown"
    installed_version: str = ""
    bundled_version: str = ""

    @property
    def upgrade_version(self) -> str:
        installed = version_tuple(self.installed_version)
        bundled = version_tuple(self.bundled_version)
        if self.installed == "yes" and installed and bundled > installed:
            return self.bundled_version
        return ""


class AutoDeployEngine:
    def __init__(
        self,
        assets: Path,
        host: str,
        port: int,
        password: str,
        log: LogFn,
        confirm: ConfirmFn,
    ) -> None:
        self.assets = assets
        self.manifest = load_manifest(assets)
        self.asset_names = asset_catalog(self.manifest)
        self.host = host
        self.port = port
        self.password = password
        self.log = log
        self.confirm = confirm
        self.telnet = TelnetSession()
        self.stage: str | None = None
        self.system_info = {"firmware": "unknown", "kernel": "unknown"}

    def close(self) -> None:
        self.telnet.close()

    def connect(self, timeout: int = 15) -> None:
        if self.telnet.connected:
            return
        self.telnet.open(self.host, self.port, self.password, timeout)
        self.command('test "$(id -u)" = 0 && uname -m && uname -r', live=False)
        self.log(f"Connected to {self.host}:{self.port}")

    def command(
        self,
        command: str,
        timeout: int = 60,
        live: bool = True,
        check: bool = True,
    ) -> CommandResult:
        progress = None
        if live:
            progress = lambda chunk: self.log(chunk.rstrip())
        result = self.telnet.command(command, timeout, progress)
        if check and result.code != 0:
            tail = result.output.rstrip()[-2500:]
            raise GatewayError(
                f"Gateway command failed ({result.code}).\n{tail}".strip()
            )
        return result

    def _asset(self, name: str) -> Path:
        return verify_asset(self.assets, self.manifest, name)

    def _plan(self, components: set[str]) -> list[str]:
        plan = ["post-init-modular-0.3.0.tar.gz"]
        if "openssh" in components:
            plan.append(self.asset_names["mi_gateway_2_openssh_deploy"])
        if "tun" in components:
            plan.append(self.asset_names["mi_gateway_2_tun_deploy"])
        if "ble-cache" in components:
            plan.append(self.asset_names["ble-spec-cache"])
        if "otbr" in components:
            plan.extend(
                [
                    self.asset_names["rcp-native"],
                    self.asset_names["rcp-mode"],
                    self.asset_names["rcp-openmiio"],
                    self.asset_names["mi-gw2-otbr"],
                    self.asset_names["spinel-probe"],
                ]
            )
        plan.append("openmiio_agent-1.2.1-arm")
        return list(dict.fromkeys(plan))

    @contextmanager
    def transfer_session(self, names: Iterable[str]):
        names = list(dict.fromkeys(names))
        local_ip = local_ip_towards(self.host, self.port)
        secret = ftp_secret()
        files = {name: self._asset(name) for name in names}
        firewall = TemporaryFirewall(local_ip, self.host)
        firewall.add()
        try:
            with ReadOnlyFTPServer(local_ip, secret, files):
                self.stage = f"/tmp/mi-gw2-python-{uuid.uuid4().hex}"
                self.command(f"umask 077; mkdir -p {shlex.quote(self.stage)}", live=False)
                for name in names:
                    expected = self.manifest[name]
                    url = f"ftp://deploy:{secret}@{local_ip}:21221/{name}"
                    self.log(f"Transferring {name}")
                    command = (
                        f"cd {shlex.quote(self.stage)} && "
                        f"wget -T 60 -O {shlex.quote(name)}.part {shlex.quote(url)} && "
                        f"mv {shlex.quote(name)}.part {shlex.quote(name)} && "
                        f"printf '%s  %s\\n' {expected} {shlex.quote(name)} | sha256sum -c -"
                    )
                    result = self.command(command, timeout=180, live=False)
                    if result.code != 0:
                        raise GatewayError(f"Gateway rejected asset {name}.")
                self.log("Gateway transfer and SHA256 verification passed")
                yield
        finally:
            if self.stage and self.telnet.connected:
                try:
                    self.command(f"rm -rf {shlex.quote(self.stage)}", live=False)
                except Exception:
                    pass
            firewall.remove()
            self.stage = None

    def extract(self, asset_name: str, root_name: str) -> str:
        if not self.stage:
            raise RuntimeError("No transfer session.")
        asset = f"{self.stage}/{asset_name}"
        root = f"{self.stage}/{root_name}"
        self.command(
            f"tar -xzf {shlex.quote(asset)} -C {shlex.quote(self.stage)} && "
            f"cd {shlex.quote(root)} && sha256sum -c SHA256SUMS >/dev/null",
            timeout=120,
            live=False,
        )
        self.log(f"Verified and extracted {asset_name}")
        return root

    def install_root(self, root_name: str) -> None:
        if not self.stage:
            raise RuntimeError("No transfer session.")
        script = "install-modular.sh" if root_name == "post-init-modular" else "install.sh"
        self.command(
            f"cd {shlex.quote(self.stage + '/' + root_name)} && sh {script}",
            timeout=300,
        )

    def status(self) -> dict[str, ComponentStatus]:
        result = self.command(self.status_command(), timeout=30, live=False)
        text = result.output
        mapping = {
            "openssh": ("STATUS_OPENSSH_INSTALL", "STATUS_OPENSSH_RUN"),
            "tun": ("STATUS_TUN_INSTALL", "STATUS_TUN_RUN"),
            "ble-cache": ("STATUS_BLE_INSTALL", "STATUS_BLE_RUN"),
            "otbr": ("STATUS_OTBR_INSTALL", "STATUS_OTBR_RUN"),
        }
        statuses: dict[str, ComponentStatus] = {}
        for component, (install_key, run_key) in mapping.items():
            installed = self._status_value(text, install_key)
            reported_version = self._status_value(text, install_key.removesuffix("_INSTALL") + "_VERSION")
            stem = COMPONENT_ASSETS[component]
            statuses[component] = ComponentStatus(
                installed,
                self._status_value(text, run_key),
                reported_version if installed == "yes" and version_tuple(reported_version) else "",
                asset_version(stem, self.asset_names[stem]),
            )
        self.system_info = {
            "firmware": self._status_value(text, "FIRMWARE_VERSION"),
            "kernel": self._status_value(text, "KERNEL_VERSION"),
        }
        self.log(text.rstrip())
        self.log("COMPONENT_STATUS_UPDATED")
        return statuses

    @staticmethod
    def _status_value(text: str, key: str) -> str:
        match = re.search(rf"(?m)^{re.escape(key)}=([^\r\n]*)", text)
        return match.group(1).strip() if match else "unknown"

    @staticmethod
    def status_command() -> str:
        command = r'''
component_version() {
    if [ "$1" != yes ]; then
        echo absent
    elif [ -f "$2/VERSION" ]; then
        head -n 1 "$2/VERSION"
    else
        CHECKSUMS=$(cat)
        PRIMARY=${CHECKSUMS%%__GW2_ALTERNATIVE__*}
        if printf '%s\n' "$PRIMARY" | sed '/^$/d' | sha256sum -c - >/dev/null 2>&1; then
            echo 0.3.0
        elif [ "$PRIMARY" != "$CHECKSUMS" ] &&
             printf '%s\n' "${CHECKSUMS#*__GW2_ALTERNATIVE__}" | sed '/^$/d' | sha256sum -c - >/dev/null 2>&1; then
            echo 0.3.0
        else
            echo unknown
        fi
    fi
}
printf "PROJECT_VERSION="; cat /data/mi-gw2-post-init/VERSION 2>/dev/null || echo absent
printf "FIRMWARE_VERSION="; printf '%s_%s\n' "$(agetprop ro.sys.mi_fw_ver 2>/dev/null)" "$(agetprop ro.sys.mi_build_num 2>/dev/null)"
printf "KERNEL_VERSION="; cat /proc/version
printf "POST_INIT_API="; grep -q "^# MI-GW2-POST-INIT-API: 1$" /data/scripts/post_init.sh 2>/dev/null && echo 1 || echo absent
printf "MODULES="; /data/mi-gw2-post-init/post-initctl.sh list 2>/dev/null | tr "\n" "," || echo absent; echo
if [ -f /data/openssh/start-ssh.sh ] && [ -x /data/openssh/sbin/sshd ]; then SSH_INSTALL=yes; elif [ -e /data/openssh ]; then SSH_INSTALL=partial; else SSH_INSTALL=no; fi
SSH_RUN=no
P=$(cat /var/run/openssh-test.pid 2>/dev/null || :)
EXE=$(readlink "/proc/$P/exe" 2>/dev/null || :)
[ "$EXE" = /data/openssh/sbin/sshd ] && SSH_RUN=yes
printf "STATUS_OPENSSH_INSTALL=%s\n" "$SSH_INSTALL"
printf "STATUS_OPENSSH_RUN=%s\n" "$SSH_RUN"
printf "STATUS_OPENSSH_VERSION="
component_version "$SSH_INSTALL" /data/openssh <<'GW2_VERSION_OPENSSH'
__LEGACY_OPENSSH__
GW2_VERSION_OPENSSH
if [ -f /data/tun/start-tun.sh ] && [ -f /data/tun/tun.ko ]; then TUN_INSTALL=yes; elif [ -e /data/tun ]; then TUN_INSTALL=partial; else TUN_INSTALL=no; fi
TUN_RUN=no
if grep -q '^tun ' /proc/modules 2>/dev/null && [ -c /dev/net/tun ]; then TUN_RUN=yes; elif grep -q '^tun ' /proc/modules 2>/dev/null; then TUN_RUN=waiting; fi
printf "STATUS_TUN_INSTALL=%s\n" "$TUN_INSTALL"
printf "STATUS_TUN_RUN=%s\n" "$TUN_RUN"
printf "STATUS_TUN_VERSION="
component_version "$TUN_INSTALL" /data/tun <<'GW2_VERSION_TUN'
__LEGACY_TUN__
GW2_VERSION_TUN
if [ -f /data/ble-spec-cache/start.sh ] && [ -x /data/ble-spec-cache/ble-cache-clock ] && [ -f /data/ble-spec-cache/installed ]; then BLE_INSTALL=yes; elif [ -e /data/ble-spec-cache ]; then BLE_INSTALL=partial; else BLE_INSTALL=no; fi
BLE_RUN=no
BP=$(cat /tmp/gw2-ble-cache-clock.pid 2>/dev/null || :)
BEXE=$(readlink "/proc/$BP/exe" 2>/dev/null || :)
if [ "$BEXE" = /data/ble-spec-cache/ble-cache-clock ]; then
    BLE_RUN=waiting
    for OP in $(pidof openmiio_agent 2>/dev/null); do
        grep -q '"runtime_pid":'"$OP"'[,}]' /tmp/gw2-ble-spec-cache-status.json 2>/dev/null && { BLE_RUN=yes; break; }
    done
fi
printf "STATUS_BLE_INSTALL=%s\n" "$BLE_INSTALL"
printf "STATUS_BLE_RUN=%s\n" "$BLE_RUN"
printf "STATUS_BLE_VERSION="
component_version "$BLE_INSTALL" /data/ble-spec-cache <<'GW2_VERSION_BLE'
__LEGACY_BLE__
GW2_VERSION_BLE
if [ -f /data/otbr/start.sh ] && [ -x /data/otbr/mi-otbr-host ] && [ -f /data/otbr/boot-manager.sh ]; then OTBR_INSTALL=yes; elif [ -e /data/otbr ]; then OTBR_INSTALL=partial; else OTBR_INSTALL=no; fi
OTBR_RUN=no
[ -n "$(pidof mi-otbr-host 2>/dev/null)" ] && OTBR_RUN=yes
if [ "$OTBR_RUN" = no ] && [ -r /tmp/mi-otbr-supervisor.lock/pid ]; then
    SP=$(cat /tmp/mi-otbr-supervisor.lock/pid 2>/dev/null || :)
    SCMD=$(tr '\000' ' ' < "/proc/$SP/cmdline" 2>/dev/null || :)
    case "$SCMD" in *'/data/otbr/'*) OTBR_RUN=waiting;; esac
fi
printf "STATUS_OTBR_INSTALL=%s\n" "$OTBR_INSTALL"
printf "STATUS_OTBR_RUN=%s\n" "$OTBR_RUN"
printf "STATUS_OTBR_VERSION="
component_version "$OTBR_INSTALL" /data/otbr <<'GW2_VERSION_OTBR'
__LEGACY_OTBR__
GW2_VERSION_OTBR
printf "OPENMIIO_PID="; pidof openmiio_agent 2>/dev/null || echo absent
printf "UART_OWNERS="; fuser /dev/ttyS1 2>/dev/null || echo none; echo
'''.strip()
        for component, label in (
            ("openssh", "OPENSSH"), ("tun", "TUN"), ("ble-cache", "BLE"), ("otbr", "OTBR")
        ):
            checksums = "\n".join(f"{digest}  {path}" for path, digest in LEGACY_030[component].items())
            if component == "otbr":
                checksums += "\n__GW2_ALTERNATIVE__\n" + "\n".join(
                    f"{digest}  {path}" for path, digest in LEGACY_030_GITHUB_OTBR.items()
                )
            command = command.replace(f"__LEGACY_{label}__", checksums)
        return command

    def ensure_openmiio(self) -> None:
        if not self.stage:
            raise RuntimeError("No transfer session.")
        remote = f"{self.stage}/openmiio_agent-1.2.1-arm"
        command = r'''
MINIMUM="1.2.1"
REMOTE=__REMOTE__
CURRENT=
if [ -f /data/openmiio_agent ]; then
    PROBE=/tmp/openmiio-writecheck.$$
    PROBELOG=$PROBE.log
    cp /data/openmiio_agent "$PROBE" || { echo OPENMIIO_VERSION_PROBE_COPY_FAILED; exit 1; }
    chmod 700 "$PROBE"
    "$PROBE" >"$PROBELOG" 2>&1 &
    PROBEPID=$!
    sleep 1
    kill "$PROBEPID" 2>/dev/null || :
    wait "$PROBEPID" 2>/dev/null || :
    CURRENT=$(sed -n 's/.*openmiio_agent version \([0-9][0-9.]*\).*/\1/p' "$PROBELOG" | tail -n 1)
    rm -f "$PROBE" "$PROBELOG"
    [ -n "$CURRENT" ] || { echo OPENMIIO_VERSION_UNKNOWN_REFUSE_REPLACE; exit 1; }
fi
version_ge() {
    awk -v current="$1" -v minimum="$2" 'BEGIN { na=split(current,A,"."); nb=split(minimum,B,"."); for (i=1;i<=3;i++) { a=(i<=na && A[i] != "" ? A[i]+0 : 0); b=(i<=nb && B[i] != "" ? B[i]+0 : 0); if (a>b) exit 0; if (a<b) exit 1 } exit 0 }'
}
RUNNING=no; RUNNING_PID=; OLD_ARGS=
if pidof openmiio_agent >/dev/null 2>&1; then
    RUNNING=yes
    for PID in $(pidof openmiio_agent); do
        EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || :)
        case "$EXE" in /data/openmiio_agent|'/data/openmiio_agent (deleted)') ;; *) echo "OPENMIIO_EXE_MISMATCH pid=$PID exe=$EXE"; exit 1;; esac
        [ -z "$RUNNING_PID" ] || { echo MULTIPLE_OPENMIIO_PROCESSES; exit 1; }
        RUNNING_PID=$PID
        OLD_ARGS=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null) || { echo OPENMIIO_ARGS_READ_FAILED; exit 1; }
    done
fi
if [ -n "$CURRENT" ] && version_ge "$CURRENT" "$MINIMUM"; then
    echo "EXISTING_OPENMIIO_RETAINED current=$CURRENT minimum=$MINIMUM"
    [ "$RUNNING" = yes ] || /data/openmiio_agent miio mqtt cache central </dev/null >/var/log/openmiio.log 2>&1 &
else
    echo "OPENMIIO_UPGRADE_REQUIRED current=${CURRENT:-missing} minimum=$MINIMUM"
    if [ "$RUNNING" = yes ]; then
        kill "$RUNNING_PID" 2>/dev/null || :
        N=0; while kill -0 "$RUNNING_PID" 2>/dev/null && [ "$N" -lt 8 ]; do sleep 1; N=$((N + 1)); done
        kill -0 "$RUNNING_PID" 2>/dev/null && { echo OPENMIIO_STOP_TIMEOUT; exit 1; }
    fi
    [ ! -f /data/openmiio_agent ] || cp /data/openmiio_agent /data/openmiio_agent.previous 2>/dev/null || :
    cp "$REMOTE" /data/openmiio_agent.new && chmod 755 /data/openmiio_agent.new && mv /data/openmiio_agent.new /data/openmiio_agent
    sleep 1
    if [ "$RUNNING" = yes ] && pidof openmiio_agent >/dev/null 2>&1; then
        echo OPENMIIO_RESTARTED_BY_EXISTING_SUPERVISOR
    elif [ "$RUNNING" = yes ]; then
        case "$OLD_ARGS" in /data/openmiio_agent\ *) ;; *) OLD_ARGS='/data/openmiio_agent miio mqtt cache central ' ;; esac
        set -f; set -- $OLD_ARGS; "$@" </dev/null >/var/log/openmiio.log 2>&1 &
    else
        /data/openmiio_agent miio mqtt cache central </dev/null >/var/log/openmiio.log 2>&1 &
    fi
fi
sleep 2; pidof openmiio_agent >/dev/null
'''.strip().replace("__REMOTE__", shlex.quote(remote))
        self.command(command, timeout=60)

    def rcp_ready(self) -> bool:
        if not self.stage:
            return False
        probe = shlex.quote(self.stage + "/" + self.asset_names["spinel-probe"])
        result = self.command(f"chmod 700 {probe}; {probe} 2>&1 || true", timeout=60)
        ready = "SPINEL_RCP_PROBE_PASS" in result.output
        self.log("Target RCP 2.5.3.0 / 115200 already running; firmware flash skipped" if ready else "Target RCP 2.5.3.0 / 115200 probe did not pass")
        return ready

    def flash_rcp(self) -> None:
        if not self.stage:
            raise RuntimeError("No transfer session.")
        if not self.confirm("确认刷写 RCP", "未检测到匹配的 RCP 2.5.3.0 / 115200。将暂停原厂服务并刷入配套固件，继续吗？"):
            raise GatewayError("用户取消了 RCP 固件刷写。")
        self.extract(self.asset_names["rcp-native"], "rcp-native")
        self.command("mkdir -p /data/mi-gw2-gui; date > /data/mi-gw2-gui/rcp-flash-in-progress", live=False)
        self.radio_write_started = True
        command = (
            f"rm -rf /tmp/rcp-native && cp -a {shlex.quote(self.stage + '/rcp-native')} /tmp/rcp-native && "
            "cd /tmp/rcp-native && sh prepare-local.sh && sh flash-rcp.sh && sync && sleep 10"
        )
        self.command(command, timeout=300)
        if not self.rcp_ready():
            raise GatewayError("RCP 刷写后 Spinel 校验失败。")
        self.command("rm -f /data/mi-gw2-gui/rcp-flash-in-progress", live=False)
        self.log("RCP_FLASH_AND_VERIFY_PASS")

    def resume_openmiio_after_rcp(self) -> None:
        command = r'''
STATE=/tmp/rcp-native/state/paused-pids
[ -r "$STATE" ] || exit 0
while IFS= read -r PID; do
    case "$PID" in ''|*[!0-9]*) continue;; esac
    grep -q '^State:[[:space:]]*T' "/proc/$PID/status" 2>/dev/null || continue
    EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || :)
    CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null || :)
    case "$EXE:$CMD" in
        '/data/openmiio_agent:/data/openmiio_agent miio mqtt cache central '|*/busybox:sh\ /data/rcp-openmiio/openmiio_agent.guard.sh\ |*/busybox:/bin/sh\ /data/rcp-openmiio/openmiio_agent.guard.sh\ )
            kill -CONT "$PID" || exit 1
            echo "OPENMIIO_RESUMED_AFTER_RCP=$PID"
            ;;
    esac
done < "$STATE"
'''.strip()
        self.command(command, timeout=30)

    def wait_for_clean_openmiio(self) -> None:
        self.command(r'''
N=0
while [ "$N" -lt 30 ]; do
    for PID in $(pidof openmiio_agent 2>/dev/null); do
        [ "$(readlink "/proc/$PID/exe" 2>/dev/null)" = /data/openmiio_agent ] || continue
        CMD=$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null || :)
        [ "$CMD" = '/data/openmiio_agent miio mqtt cache central ' ] || continue
        PROC_STATE=$(awk '/^State:/{print $2; exit}' "/proc/$PID/status" 2>/dev/null)
        case "$PROC_STATE" in ''|T*|t*|Z*|X*) continue;; esac
        echo "OPENMIIO_READY_FOR_BLE_CACHE=$PID"
        exit 0
    done
    sleep 1
    N=$((N + 1))
done
echo 'The RCP openmiio supervisor did not start a running BLE/Mesh process.'
exit 1
'''.strip(), timeout=40)

    @contextmanager
    def pause_otbr_for_upgrade(self, selected: bool):
        self.radio_write_started = False
        paused = False
        if selected:
            result = self.command(
                "if [ -x /data/otbr/stop.sh ] && "
                "{ pidof mi-otbr-host >/dev/null 2>&1 || [ -r /tmp/mi-otbr-supervisor.pid ]; }; then "
                "sh /data/otbr/stop.sh && echo OTBR_PAUSED_FOR_UPGRADE; fi",
                timeout=90,
                live=False,
            )
            paused = "OTBR_PAUSED_FOR_UPGRADE" in result.output.splitlines()
        try:
            yield
        except Exception:
            if paused and not self.radio_write_started and self.telnet.connected:
                try:
                    self.command("sh /data/otbr/start.sh", timeout=90)
                    self.log("OTBR_PREVIOUS_HOST_RESTARTED")
                except Exception as exc:
                    self.log(f"OTBR_PREVIOUS_HOST_RESTART_FAILED: {exc}")
            raise

    def deploy(self, components: set[str], options: DeployOptions) -> str | None:
        if not components:
            raise ValueError("至少选择一个组件。")
        plan = self._plan(components)
        with self.transfer_session(plan), self.pause_otbr_for_upgrade("otbr" in components):
            if "otbr" in components:
                otbr = self.extract(self.asset_names["mi-gw2-otbr"], "otbr-deploy")
                self.command(
                    "if [ -f /data/otbr/config.yaml ]; then "
                    f"if cmp -s {shlex.quote(otbr + '/examples/config.example')} /data/otbr/config.yaml && "
                    "{ [ ! -f /data/otbr/secrets.yaml ] || "
                    f"cmp -s {shlex.quote(otbr + '/examples/secrets.example')} /data/otbr/secrets.yaml; }}; then "
                    "echo OTBR_CONFIG_TEMPLATE_DETECTED; else "
                    f"{shlex.quote(otbr + '/payload/mi-otbr-host')} /data/otbr/config.yaml --check-config; fi; fi",
                    timeout=30,
                    live=False,
                )
                marker = self.command(
                    "if [ -f /data/mi-gw2-gui/rcp-flash-in-progress ]; then "
                    "echo RCP_FLASH_MARKER_PRESENT; cat /data/mi-gw2-gui/rcp-flash-in-progress; "
                    "else echo RCP_FLASH_MARKER_ABSENT; fi",
                    live=False,
                )
                if self.marker_present(marker.output):
                    self.log("RCP_INTERRUPT_MARKER_PRESENT")
                    self.log(marker.output.rstrip())
                    if self.rcp_ready():
                        self.command("rm -f /data/mi-gw2-gui/rcp-flash-in-progress", live=False)
                        self.log("RCP_INTERRUPT_MARKER_CLEARED: current RCP probe passed")
                    else:
                        if not self.confirm(
                            "检测到 RCP 中断标记",
                            "网关存在上次刷写未正常收尾的标记，但当前 Spinel 探测未通过。\n\n"
                            "如果已经通过独立的原生恢复流程刷回原厂 NCP，并在网关应用中确认工作正常，"
                            "可以选择清除过期标记。清除后，启用“安装OTBR时自动刷入RCP固件”会继续本次部署。\n\n"
                            "只在确认当前无线模块处于已知原厂 NCP 状态时继续。清除标记并继续吗？",
                        ):
                            raise GatewayError("用户保留了 RCP 刷写中断标记。")
                        self.command("rm -f /data/mi-gw2-gui/rcp-flash-in-progress", live=False)
                        self.log("RCP_INTERRUPT_MARKER_CLEARED_AFTER_USER_CONFIRMATION")
            self.extract("post-init-modular-0.3.0.tar.gz", "post-init-modular")
            self.install_root("post-init-modular")
            if "openssh" in components:
                self.extract(self.asset_names["mi_gateway_2_openssh_deploy"], "mi_gateway_2_openssh_deploy")
                self.install_root("mi_gateway_2_openssh_deploy")
            if "tun" in components:
                self.extract(self.asset_names["mi_gateway_2_tun_deploy"], "mi_gateway_2_tun_deploy")
                self.install_root("mi_gateway_2_tun_deploy")
            if components & {"otbr", "ble-cache"}:
                self.ensure_openmiio()
            if "otbr" in components:
                self.extract(self.asset_names["rcp-native"], "rcp-native")
                if not self.rcp_ready():
                    if not options.flash_rcp:
                        raise GatewayError("未检测到匹配的 RCP 2.5.3.0 / 115200，且未启用自动刷写。")
                    self.flash_rcp()
                self.extract(self.asset_names["rcp-mode"], "rcp-mode")
                self.install_root("rcp-mode")
                self.extract(self.asset_names["rcp-openmiio"], "rcp-openmiio")
                self.install_root("rcp-openmiio")
                self.resume_openmiio_after_rcp()
                self.command("sh /data/rcp-openmiio/start.sh --now", timeout=60)
                if "ble-cache" in components:
                    self.wait_for_clean_openmiio()
            if "ble-cache" in components:
                self.extract(self.asset_names["ble-spec-cache"], "ble-spec-cache")
                self.install_root("ble-spec-cache")
            if "otbr" in components:
                self.install_root("otbr-deploy")
            self.command("sh /data/mi-gw2-post-init/post-initctl.sh check", live=False)
            self.log("APPLY_COMPLETE components=" + ",".join(sorted(components)))
        return self._reboot_and_verify(components, options)

    @staticmethod
    def marker_present(output: str) -> bool:
        return bool(re.search(r"(?m)^RCP_FLASH_MARKER_PRESENT\r?$", output))

    def _reboot_and_verify(self, components: set[str], options: DeployOptions) -> str | None:
        pending_message = None
        if "otbr" in components:
            result = self.command(r'''
if sh /data/otbr/check.sh >/tmp/mi-otbr-config.log 2>&1; then
    exit 0
fi
if [ ! -f /data/otbr/config.yaml ] ||
   { cmp -s /data/otbr/config.yaml.example /data/otbr/config.yaml &&
     { [ ! -f /data/otbr/secrets.yaml ] || cmp -s /data/otbr/secrets.yaml.example /data/otbr/secrets.yaml; }; }; then
    echo OTBR_CONFIG_REQUIRED
    exit 0
fi
echo OTBR_CONFIG_INVALID
cat /tmp/mi-otbr-config.log
exit 1
'''.strip(), timeout=30, live=False)
            if "OTBR_CONFIG_REQUIRED" in result.output.splitlines():
                pending_message = "OTBR 已安装，等待配置"
                self.log(pending_message + "。请用「更新 OTBR 配置」上传有效配置，然后重启 OTBR。")
        if not options.reboot:
            return pending_message
        if not self.confirm("确认重启", "组件已部署。现在重启网关以完整验证启动模块？"):
            return pending_message
        self.reboot()
        if "openssh" in components:
            verify = r'''
N=0
while [ "$N" -lt 30 ]; do
    MODULES=$(/data/mi-gw2-post-init/post-initctl.sh list 2>/dev/null | tr '\n' ',')
    PID=$(cat /var/run/openssh-test.pid 2>/dev/null || :)
    EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || :)
    MODULE_OK=no
    case ",$MODULES" in *,openssh,*) MODULE_OK=yes;; esac
    if [ "$EXE" = /data/openssh/sbin/sshd ] && [ "$MODULE_OK" = yes ]; then
        echo APPLY_VERIFY_PASS_AFTER_REBOOT
        exit 0
    fi
    sleep 1; N=$((N + 1))
done
exit 1
'''.strip()
            self.command(verify, timeout=60)
            self.log("APPLY_VERIFY_PASS_AFTER_REBOOT components=openssh")
        if "otbr" in components and pending_message is None:
            verify = r'''
N=0
while [ "$N" -lt 90 ]; do
    MODULES=$(/data/mi-gw2-post-init/post-initctl.sh list 2>/dev/null | tr '\n' ',')
    HOST=$(pidof mi-otbr-host 2>/dev/null || :)
    MODULE_OK=no
    case ",$MODULES" in *,otbr,*) MODULE_OK=yes;; esac
    if [ -n "$HOST" ] && [ "$MODULE_OK" = yes ]; then
        echo OTBR_VERIFY_PASS_AFTER_REBOOT
        exit 0
    fi
    sleep 2; N=$((N + 1))
done
echo OTBR_VERIFY_TIMEOUT
sh /data/otbr/status.sh 2>/dev/null || :
exit 1
'''.strip()
            self.command(verify, timeout=210)
            self.log("APPLY_VERIFY_PASS_AFTER_REBOOT components=otbr")
        return pending_message

    def uninstall(self, components: set[str], options: DeployOptions) -> None:
        if not components:
            raise ValueError("至少选择一个组件。")
        if "otbr" in components:
            self.command(
                "if [ -x /data/otbr/uninstall.sh ]; then sh /data/otbr/uninstall.sh || true; fi; "
                "/data/mi-gw2-post-init/post-initctl.sh remove otbr >/dev/null 2>&1 || true",
                timeout=120,
            )
            self.command(
                "if [ -f /data/rcp-openmiio/uninstall.sh ]; then sh /data/rcp-openmiio/uninstall.sh || true; fi; "
                "if [ -f /tmp/rcp-openmiio.lock/pid ]; then P=$(cat /tmp/rcp-openmiio.lock/pid 2>/dev/null || true); "
                'case $P in ""|*[!0-9]*) ;; *) kill $P 2>/dev/null || true ;; esac; fi',
                timeout=60,
            )
            self.command(
                "if [ -f /data/rcp-mode/uninstall.sh ]; then sh /data/rcp-mode/uninstall.sh || true; fi",
                timeout=60,
            )
            command = r'''
for ITEM in /data/otbr /data/rcp-mode /data/rcp-openmiio; do
    [ ! -e "$ITEM" ] && continue
    case "$ITEM" in
        /data/otbr) [ -f /data/otbr/mi-otbr-host ] || { echo "UNMANAGED_COMPONENT=$ITEM"; exit 1; } ;;
        /data/rcp-mode) [ -f /data/rcp-mode/apply-mode.sh ] || { echo "UNMANAGED_COMPONENT=$ITEM"; exit 1; } ;;
        /data/rcp-openmiio) [ -f /data/rcp-openmiio/start.sh ] || { echo "UNMANAGED_COMPONENT=$ITEM"; exit 1; } ;;
    esac
    rm -rf "$ITEM"
    echo "COMPONENT_FILES_REMOVED=$ITEM"
done
rm -f /tmp/mi-otbr.pid /tmp/mi-otbr.stop /tmp/rcp-openmiio.stock-ready
rm -rf /tmp/mi-otbr-supervisor.lock
'''.strip()
            self.command(command, timeout=60)
        if "ble-cache" in components:
            self.command(
                "if [ -x /data/ble-spec-cache/uninstall.sh ]; then sh /data/ble-spec-cache/uninstall.sh || true; "
                "else /data/mi-gw2-post-init/post-initctl.sh remove ble-cache || true; fi",
                timeout=120,
            )
            command = r'''
if [ -e /data/ble-spec-cache ]; then
    [ -f /data/ble-spec-cache/installed ] || { echo UNMANAGED_COMPONENT=/data/ble-spec-cache; exit 1; }
    rm -rf /data/ble-spec-cache
    echo COMPONENT_FILES_REMOVED=/data/ble-spec-cache
fi
if [ -e /data/openmiio_agent.lua ]; then
    rm -f /data/openmiio_agent.lua
    echo COMPONENT_FILES_REMOVED=/data/openmiio_agent.lua
fi
rm -f /tmp/gw2-ble-spec-cache-status.json /tmp/gw2-ble-cache-clock.pid /tmp/gw2-ble-cache-clock.lock
'''.strip()
            self.command(command, timeout=30)
        if "tun" in components:
            self.command(
                "if [ -x /data/tun/uninstall-autostart.sh ]; then sh /data/tun/uninstall-autostart.sh || true; "
                "else /data/mi-gw2-post-init/post-initctl.sh remove tun || true; fi; "
                'if [ -c /dev/net/tun ] && [ -z "$(fuser /dev/net/tun 2>/dev/null || true)" ]; then '
                "rm -f /dev/net/tun; rmmod tun 2>/dev/null || true; fi",
                timeout=60,
            )
            command = r'''
if [ -e /data/tun ]; then
    [ -f /data/tun/.mi-gateway2-tun-managed ] || { echo UNMANAGED_COMPONENT=/data/tun; exit 1; }
    rm -rf /data/tun
    echo COMPONENT_FILES_REMOVED=/data/tun
fi
'''.strip()
            self.command(command, timeout=30)
        if "openssh" in components:
            self.command(
                "/data/mi-gw2-post-init/post-initctl.sh remove openssh || true; "
                "if [ -r /var/run/openssh-test.pid ]; then P=$(cat /var/run/openssh-test.pid 2>/dev/null || true); "
                'EXE=$(readlink /proc/$P/exe 2>/dev/null || true); '
                '[ "$EXE" = /data/openssh/sbin/sshd ] && kill $P 2>/dev/null || true; fi',
                timeout=30,
            )
            command = r'''
if [ -e /data/openssh ]; then
    [ -f /data/openssh/start-ssh.sh ] || { echo UNMANAGED_COMPONENT=/data/openssh; exit 1; }
    rm -rf /data/openssh
    echo COMPONENT_FILES_REMOVED=/data/openssh
fi
rm -f /var/run/openssh-test.pid
if [ -f /res/passwd ] && grep -q '^sshd:' /res/passwd; then
    TMP=/res/passwd.openssh-uninstall.$$
    if awk -F: 'BEGIN {OFS=":"} $1=="sshd" && $3>=65000 && $3<=65534 && $6=="/var/empty" && $7=="/bin/false" {next} {print}' /res/passwd > "$TMP" &&
        cp "$TMP" /res/passwd; then
        rm -f "$TMP"
        echo OPENSSH_SERVICE_ACCOUNT=removed
    else
        rm -f "$TMP"
        echo OPENSSH_SERVICE_ACCOUNT=cleanup_failed
    fi
fi
'''.strip()
            self.command(command, timeout=30)
        self.command("sh /data/mi-gw2-post-init/post-initctl.sh check || true", live=False)
        self.log("UNINSTALL_PURGE_COMPLETE components=" + ",".join(sorted(components)))
        if options.reboot and self.confirm("确认重启", "卸载完成。现在重启以清除 RCP 绑定挂载并验证启动链？"):
            self.reboot()

    def restore_stock(self, options: DeployOptions) -> None:
        message = (
            "将卸载全部项目组件、刷回原厂 Zigbee，并删除项目程序和目录。继续吗？"
            if options.full_restore
            else "将移除所有项目启动模块并恢复原厂启动入口。RCP 固件和程序目录会保留。继续吗？"
        )
        if not self.confirm("恢复原厂", message):
            return
        plan = ["post-init-modular-0.3.0.tar.gz"]
        if options.full_restore:
            plan.append(self.asset_names["rcp-native"])
        with self.transfer_session(plan):
            post = self.extract("post-init-modular-0.3.0.tar.gz", "post-init-modular")
            if options.full_restore:
                self.extract(self.asset_names["rcp-native"], "rcp-native")
                command = (
                    "if [ -x /tmp/rcp-native/restore-services.sh ]; then sh /tmp/rcp-native/restore-services.sh || true; fi; "
                    "rm -rf /tmp/rcp-native; "
                    f"cp -a {shlex.quote(self.stage + '/rcp-native')} /tmp/rcp-native; "
                    f"cd {shlex.quote(post)}; sh factory-reset.sh --prepare-flash; "
                    "cd /tmp/rcp-native; "
                    "if sh prepare-local.sh; then "
                    "if sh flash-zigbee.sh; then sh restore-services.sh; "
                    "else sh restore-services.sh || true; exit 1; fi; "
                    "else exit 1; fi"
                )
                self.command(command, timeout=360)
            mode = "--remove-all" if options.full_restore else "--restore-hook"
            self.command(f"cd {shlex.quote(post)} && sh factory-reset.sh {mode}", timeout=240)
            if not options.full_restore:
                self.command(
                    "if [ -x /data/otbr/stop.sh ]; then sh /data/otbr/stop.sh || true; fi; "
                    "if [ -x /data/ble-spec-cache/stop.sh ]; then sh /data/ble-spec-cache/stop.sh || true; fi"
                )
        self.log("FACTORY_RESTORE_COMPLETE" if options.full_restore else "SOFT_RESTORE_COMPLETE")
        if options.reboot and self.confirm("确认重启", "恢复完成。现在重启网关？"):
            self.reboot()
            if options.full_restore:
                self._verify_factory()

    def _verify_factory(self) -> None:
        command = r'''
RESIDUE=
for P in /data/openssh /data/tun /data/rcp-mode /data/rcp-openmiio /data/otbr /data/ble-spec-cache /data/mi-gw2-post-init /data/mi-gw2-auto /data/mi-gw2-gui /data/openmiio_agent.lua /data/openmiio_agent.lua.new /data/openmiio_agent.new /data/openmiio_agent.previous; do
    [ ! -e "$P" ] && [ ! -L "$P" ] || RESIDUE="$RESIDUE $P"
done
if [ -e /data/scripts/post_init.sh ] && grep -Eq 'MI-GW2-POST-INIT-API|BEGIN MI-GW2 POST-INIT (MODULE|STOCK ANCHOR)' /data/scripts/post_init.sh; then RESIDUE="$RESIDUE /data/scripts/post_init.sh:project-markers"; fi
for TARGET in /bin/fw_manager.sh /bin/app_monitor.sh; do awk -v target="$TARGET" '$2 == target {found=1} END {exit !found}' /proc/mounts && RESIDUE="$RESIDUE $TARGET:bind"; done
[ ! -e /dev/net/tun ] || RESIDUE="$RESIDUE /dev/net/tun"
grep -q '^tun ' /proc/modules 2>/dev/null && RESIDUE="$RESIDUE kernel:tun"
for D in /proc/[0-9]*; do
    PID=${D##*/}; [ "$PID" != "$$" ] || continue
    EXE=$(readlink "$D/exe" 2>/dev/null || :)
    CMD=$(tr '\000' ' ' 2>/dev/null <"$D/cmdline") || continue
    case "$EXE $CMD" in */data/otbr/*|*/data/openmiio_agent.new\ *|*/data/openmiio_agent.previous\ *|*/data/ble-spec-cache/*|*/data/openssh/*|*/data/rcp-openmiio/*|*/data/rcp-mode/*) RESIDUE="$RESIDUE pid:$PID";; esac
done
[ -z "$RESIDUE" ] || { echo "FACTORY_RESIDUE=$RESIDUE"; exit 1; }
[ ! -e /data/openmiio_agent ] || echo FACTORY_SHARED_OPENMIIO_PRESENT
echo FACTORY_VERIFY_PASS_AFTER_REBOOT
'''.strip()
        result = self.command(command, timeout=45, live=False)
        if "FACTORY_SHARED_OPENMIIO_PRESENT" in result.output.splitlines():
            self.log("FACTORY_SHARED_OPENMIIO_PRESENT: shared service is outside project cleanup verification after reboot.")
        self.log("FACTORY_VERIFY_PASS_AFTER_REBOOT")

    def reboot(self, timeout: int = 240) -> None:
        try:
            self.command("sync; reboot", timeout=15, live=False)
        except Exception:
            self.log("Telnet closed during reboot.")
        self.telnet.close()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                self.telnet.open(self.host, self.port, self.password, 10)
                self.log("Gateway is online after reboot.")
                return
            except Exception:
                self.log("Waiting for gateway Telnet after reboot...")
        raise GatewayError("网关重启后 240 秒内未重新上线。")

    def upload_yaml(self, path: Path, restart: bool | None = None) -> None:
        data = path.read_bytes()
        if not data:
            raise ValueError("YAML 文件为空。")
        if len(data) > 1024 * 1024:
            raise ValueError("YAML 文件超过 1 MiB。")
        tag = uuid.uuid4().hex
        stage = f"/tmp/gw2-otbr-config-{tag}"
        remote_b64 = f"{stage}/config.b64"
        remote_yaml = f"{stage}/config.yaml"
        self.command(
            f"umask 077; mkdir {shlex.quote(stage)} && : > {shlex.quote(remote_b64)} && "
            f"ln -s /data/otbr/secrets.yaml {shlex.quote(stage + '/secrets.yaml')}",
            live=False,
        )
        try:
            encoded = base64.b64encode(data).decode("ascii")
            for offset in range(0, len(encoded), 768):
                part = encoded[offset : offset + 768]
                self.command(f"printf '%s' {shlex.quote(part)} >> {shlex.quote(remote_b64)}", live=False)
            digest = __import__("hashlib").sha256(data).hexdigest()
            self.command(
                f"base64 -d {shlex.quote(remote_b64)} > {shlex.quote(remote_yaml)} && "
                f"printf '%s  %s\\n' {digest} {shlex.quote(remote_yaml)} | sha256sum -c -",
                live=False,
            )
            validation = self.command(
                f"if [ -x /data/otbr/mi-otbr-host ]; then /data/otbr/mi-otbr-host {shlex.quote(remote_yaml)} --check-config; "
                "else echo OTBR_VALIDATOR_MISSING; fi",
                check=False,
            )
            if "OTBR_VALIDATOR_MISSING" in validation.output.splitlines():
                if not self.confirm("配置未验证", "OTBR Host 尚未安装，当前无法验证 YAML。仍然创建或覆盖配置吗？"):
                    return
            elif validation.code != 0:
                raise ValueError("OTBR 配置校验失败，网关原配置已保留。\n" + validation.output.rstrip())
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.command(
                "mkdir -p /data/otbr/previous; "
                "if [ -f /data/otbr/config.yaml ]; then cp -p /data/otbr/config.yaml "
                f"'/data/otbr/previous/config.yaml.{stamp}'; fi; "
                f"chmod 600 {shlex.quote(remote_yaml)}; mv {shlex.quote(remote_yaml)} /data/otbr/config.yaml.new; "
                "mv -f /data/otbr/config.yaml.new /data/otbr/config.yaml; "
                "chmod 600 /data/otbr/config.yaml"
            )
        finally:
            if self.telnet.connected:
                self.command(
                    "rm -f " + " ".join(shlex.quote(path) for path in (remote_b64, remote_yaml, stage + "/secrets.yaml"))
                    + f"; rmdir {shlex.quote(stage)}",
                    check=False,
                    live=False,
                )
        self.log("OTBR_CONFIG_INSTALLED: /data/otbr/config.yaml")
        available = self.command(
            "if [ -x /data/otbr/restart.sh ]; then echo OTBR_RESTART_AVAILABLE; fi",
            live=False,
        )
        if "OTBR_RESTART_AVAILABLE" in available.output:
            if restart is None:
                restart = self.confirm("重启 OTBR", "配置已保存。现在重启 OTBR Host 使配置生效？")
            if restart:
                self.command("sh /data/otbr/restart.sh", timeout=120)
                self.log("OTBR_RESTARTED")
