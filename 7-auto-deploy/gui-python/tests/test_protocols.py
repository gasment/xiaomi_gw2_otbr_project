from __future__ import annotations

import ftplib
import os
import subprocess
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import AutoDeployEngine, ComponentStatus, DeployOptions
from gateway import CommandResult, GatewayError, ReadOnlyFTPServer, TelnetSession
from resources import asset_catalog, load_manifest, resolve_assets


def test_telnet_command_status() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    errors: list[Exception] = []

    def clean_line(conn: socket.socket) -> str:
        data = bytearray()
        while True:
            value = conn.recv(1)
            if not value:
                raise EOFError
            if value[0] == 255:
                verb = conn.recv(1)[0]
                if verb in (251, 252, 253, 254):
                    conn.recv(1)
                continue
            if value[0] == 10:
                return bytes(data).rstrip(b"\r").decode()
            data += value

    def server() -> None:
        try:
            with listener:
                conn, _ = listener.accept()
                with conn:
                    conn.sendall(bytes((255, 251, 1)))
                    conn.sendall(b"Mock login: ")
                    assert clean_line(conn) == "root"
                    conn.sendall(b"Password: ")
                    assert clean_line(conn) == ""
                    conn.sendall(b"\r\n~ # ")
                    assert clean_line(conn) == "("
                    assert clean_line(conn) == "false"
                    assert clean_line(conn) == ")"
                    marker_line = clean_line(conn)
                    token = marker_line.split("__GW2_", 1)[1].split(":", 1)[0]
                    conn.sendall(marker_line.encode() + b"\r\noutput\r\n")
                    conn.sendall(f"__GW2_{token}:7\r\n~ # ".encode())
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    session = TelnetSession()
    session.open("127.0.0.1", port, "", timeout=5)
    result = session.command("false", timeout=5)
    session.close()
    thread.join(2)
    assert not errors, errors
    assert result.code == 7


def test_command_exit_keeps_login_shell() -> None:
    if os.name != "posix":
        return
    with subprocess.Popen(["sh"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as shell:
        class ShellSession(TelnetSession):
            def _send(self, command: str) -> None:
                shell.stdin.write((command + "\n").encode())
                shell.stdin.flush()

            def _read(self, _timeout: int) -> str:
                return os.read(shell.stdout.fileno(), 4096).decode()

        session = ShellSession()
        try:
            assert session.command("exit 0", timeout=2).code == 0
            assert session.command("exit 1", timeout=2).code == 1
            result = session.command("printf '%s\n' SESSION_STILL_OPEN", timeout=2)
            assert result.code == 0 and "SESSION_STILL_OPEN" in result.output
        finally:
            shell.stdin.close()


def test_factory_verification_allows_shared_openmiio(tmp_path: Path) -> None:
    if os.name != "posix":
        return
    engine = object.__new__(AutoDeployEngine)
    engine.log = lambda _: None

    def command(command, **_kwargs):
        fixture_command = command.replace("/data/", f"{tmp_path}/data/")
        fixture_command = fixture_command.replace("/proc/", f"{tmp_path}/proc/")
        fixture_command = fixture_command.replace("/dev/net/tun", str(tmp_path / "tun"))
        result = subprocess.run(["sh", "-c", fixture_command], capture_output=True, text=True, check=False)
        return CommandResult(result.returncode, result.stdout + result.stderr)

    engine.command = command
    data = tmp_path / "data"
    data.mkdir()
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "mounts").touch()
    (proc / "modules").touch()
    (data / "openmiio_agent").touch()
    shared = proc / "100"
    shared.mkdir()
    (shared / "exe").symlink_to(data / "openmiio_agent")
    (shared / "cmdline").write_bytes(str(data / "openmiio_agent").encode() + b"\0miio\0mqtt\0")
    (proc / "101").mkdir()  # Process disappeared before cmdline was opened.
    original = engine.command

    def assert_verified(code):
        def check(command, **kwargs):
            result = original(command, **kwargs)
            assert result.code == code, result.output
            assert "can't open" not in result.output
            return result
        engine.command = check
        engine._verify_factory()

    assert_verified(0)
    (data / "ble-spec-cache").mkdir()
    assert_verified(1)
    (data / "ble-spec-cache").rmdir()
    (shared / "exe").unlink()
    (shared / "exe").symlink_to(data / "otbr/mi-otbr-host")
    assert_verified(1)
    (shared / "exe").unlink()
    (shared / "exe").symlink_to(data / "openmiio_agent")
    (data / "openmiio_agent.lua").touch()
    assert_verified(1)


def test_otbr_pending_config_skips_runtime_wait(tmp_path: Path) -> None:
    if os.name != "posix":
        return
    engine = object.__new__(AutoDeployEngine)
    engine.log = lambda _: None
    engine.confirm = lambda *_: True
    engine.reboot = lambda: events.append("rebooted")
    events = []
    config, example = tmp_path / "config.yaml", tmp_path / "config.yaml.example"
    config.write_text("placeholder")
    example.write_text("placeholder")
    (tmp_path / "check.sh").write_text("exit 1\n")

    def command(script, **_kwargs):
        if "while [ " in script:
            events.append("runtime_wait")
            return CommandResult(0, "OTBR_VERIFY_PASS_AFTER_REBOOT")
        script = script.replace("/data/otbr/", f"{tmp_path}/")
        script = script.replace("/tmp/mi-otbr-config.log", str(tmp_path / "config.log"))
        result = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
        if result.returncode:
            raise GatewayError(result.stdout + result.stderr)
        return CommandResult(result.returncode, result.stdout)

    engine.command = command
    assert engine._reboot_and_verify({"otbr"}, DeployOptions(reboot=False)) == "OTBR 已安装，等待配置"
    assert events == []
    assert engine._reboot_and_verify({"otbr"}, DeployOptions()) == "OTBR 已安装，等待配置"
    assert events == ["rebooted"]

    config.write_text("edited and broken")
    try:
        engine._reboot_and_verify({"otbr"}, DeployOptions())
    except GatewayError as exc:
        assert "OTBR_CONFIG_INVALID" in str(exc)
    else:
        raise AssertionError("Edited invalid config was classified as a deployment success")
    assert events == ["rebooted"]

    (tmp_path / "check.sh").write_text("exit 0\n")
    assert engine._reboot_and_verify({"otbr"}, DeployOptions()) is None
    assert events[-2:] == ["rebooted", "runtime_wait"]


def test_read_only_ftp(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"gateway-package" * 4096)
    with ReadOnlyFTPServer("127.0.0.1", "secret", {payload.name: payload}):
        ftp = ftplib.FTP()
        ftp.connect("127.0.0.1", 21221, timeout=5)
        ftp.login("deploy", "secret")
        output = bytearray()
        ftp.retrbinary("RETR payload.bin", output.extend)
        ftp.quit()
    assert bytes(output) == payload.read_bytes()


def test_gateway_exit_code_is_enforced() -> None:
    class FakeTelnet:
        @staticmethod
        def command(command: str, timeout: int, progress):
            return CommandResult(1, "TUN_INSTALL_FAILED")

    engine = object.__new__(AutoDeployEngine)
    engine.telnet = FakeTelnet()
    engine.log = lambda _: None
    try:
        engine.command("false")
    except GatewayError as exc:
        assert "TUN_INSTALL_FAILED" in str(exc)
    else:
        raise AssertionError("non-zero gateway status was ignored")


def test_rcp_marker_uses_output_line_not_echoed_command() -> None:
    assert not AutoDeployEngine.marker_present(
        "if [ -f marker ]; then echo RCP_FLASH_MARKER_PRESENT; fi\n"
        "RCP_FLASH_MARKER_ABSENT\n"
    )
    assert AutoDeployEngine.marker_present("RCP_FLASH_MARKER_PRESENT\n")


def test_factory_restore_stops_before_flash_when_prepare_fails() -> None:
    source = (Path(__file__).resolve().parents[1] / "engine.py").read_text()
    assert "if sh prepare-local.sh; then " in source
    assert "sh prepare-local.sh; sh flash-zigbee.sh" not in source
    assert "else sh restore-services.sh || true; exit 1; fi" in source


def test_otbr_install_defers_stock_uart_until_reboot() -> None:
    repo = Path(__file__).resolve().parents[3]
    installer = (repo / "5-otbr/src/otbr_host/deploy/install.sh").read_text()
    engine = (repo / "7-auto-deploy/gui-python/engine.py").read_text()
    assert "UART_BUSY_STOCK_DEFERRED=" in installer
    assert "DEPLOY_INSTALLED_DEFERRED" in installer
    assert "UART_BLOCKED_BY_UNMANAGED=" in installer
    assert "OTBR_VERIFY_PASS_AFTER_REBOOT" in engine


def test_ble_cache_restart_escalates_to_sigkill() -> None:
    repo = Path(__file__).resolve().parents[3]
    reload = (
        repo / "8-xiaomi-gateway3-patch/ble-spec-cache/payload/reload-openmiio.sh"
    ).read_text()
    assert "escalating to SIGKILL" in reload
    assert "openmiio did not stop; no force kill sent" not in reload


def test_component_versions_are_independent() -> None:
    assets = resolve_assets()
    manifest = load_manifest(assets)
    ssh_name = "mi_gateway_2_openssh_deploy-0.3.0.tar.gz"
    manifest["mi_gateway_2_openssh_deploy-0.3.10.tar.gz"] = manifest.pop(ssh_name)
    engine = object.__new__(AutoDeployEngine)
    engine.asset_names = asset_catalog(manifest)
    engine.log = lambda _: None
    engine.command = lambda *_args, **_kwargs: CommandResult(
        0,
        "PROJECT_VERSION=9.9.9\n"
        "STATUS_OPENSSH_INSTALL=yes\nSTATUS_OPENSSH_RUN=yes\nSTATUS_OPENSSH_VERSION=0.3.9\n"
        "STATUS_TUN_INSTALL=yes\nSTATUS_TUN_VERSION=0.3.0\n"
        "STATUS_BLE_INSTALL=partial\nSTATUS_BLE_VERSION=0.2.0\n"
        "STATUS_OTBR_INSTALL=yes\nSTATUS_OTBR_VERSION=unknown\n",
    )
    status = engine.status()
    assert status["openssh"].installed_version == "0.3.9"
    assert status["openssh"].upgrade_version == "0.3.10"
    assert status["tun"].bundled_version == "0.3.0" and not status["tun"].upgrade_version
    assert not status["ble-cache"].installed_version and not status["ble-cache"].upgrade_version
    assert not status["otbr"].installed_version and not status["otbr"].upgrade_version
    assert "mi_gateway_2_openssh_deploy-0.3.10.tar.gz" in engine._plan({"openssh"})
    assert not ComponentStatus("yes", "yes", "0.4.0", "0.3.10").upgrade_version


if __name__ == "__main__":
    import tempfile

    test_telnet_command_status()
    test_command_exit_keeps_login_shell()
    test_component_versions_are_independent()
    test_gateway_exit_code_is_enforced()
    test_rcp_marker_uses_output_line_not_echoed_command()
    test_factory_restore_stops_before_flash_when_prepare_fails()
    test_otbr_install_defers_stock_uart_until_reboot()
    test_ble_cache_restart_escalates_to_sigkill()
    with tempfile.TemporaryDirectory() as tmp:
        test_read_only_ftp(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_factory_verification_allows_shared_openmiio(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_otbr_pending_config_skips_runtime_wait(Path(tmp))
    print("PROTOCOL_TESTS_PASS")
