from __future__ import annotations

import ftplib
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import AutoDeployEngine
from gateway import CommandResult, GatewayError, ReadOnlyFTPServer, TelnetSession


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
                    assert clean_line(conn) == "false"
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
    engine = (repo / "auto-deploy/gui-python/engine.py").read_text()
    assert "UART_BUSY_STOCK_DEFERRED=" in installer
    assert "DEPLOY_INSTALLED_DEFERRED" in installer
    assert "UART_BLOCKED_BY_UNMANAGED=" in installer
    assert "OTBR_VERIFY_PASS_AFTER_REBOOT" in engine


def test_ble_cache_restart_escalates_to_sigkill() -> None:
    repo = Path(__file__).resolve().parents[3]
    reload = (
        repo / "xiaomi_gateway3_patch/ble-spec-cache/payload/reload-openmiio.sh"
    ).read_text()
    assert "escalating to SIGKILL" in reload
    assert "openmiio did not stop; no force kill sent" not in reload


if __name__ == "__main__":
    import tempfile

    test_telnet_command_status()
    test_gateway_exit_code_is_enforced()
    test_rcp_marker_uses_output_line_not_echoed_command()
    test_factory_restore_stops_before_flash_when_prepare_fails()
    test_otbr_install_defers_stock_uart_until_reboot()
    test_ble_cache_restart_escalates_to_sigkill()
    with tempfile.TemporaryDirectory() as tmp:
        test_read_only_ftp(Path(tmp))
    print("PROTOCOL_TESTS_PASS")
