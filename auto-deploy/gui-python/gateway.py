from __future__ import annotations

import codecs
import os
import re
import secrets
import select
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

Progress = Callable[[str], None]


class GatewayError(RuntimeError):
    pass


@dataclass
class CommandResult:
    code: int
    output: str


class TelnetSession:
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self._iac_state = 0
        self._iac_verb = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def _send(self, text: str) -> None:
        if self.sock is None:
            raise GatewayError("Telnet is not connected.")
        self.sock.sendall((text + "\r\n").encode("utf-8"))

    def _plain_data(self, data: bytes) -> bytes:
        plain = bytearray()
        for value in data:
            if self._iac_state == 0:
                if value == 255:
                    self._iac_state = 1
                elif value != 0:
                    plain.append(value)
            elif self._iac_state == 1:
                if value == 255:
                    plain.append(value)
                    self._iac_state = 0
                elif value in (251, 252, 253, 254):
                    self._iac_verb = value
                    self._iac_state = 2
                elif value == 250:
                    self._iac_state = 3
                else:
                    self._iac_state = 0
            elif self._iac_state == 2:
                if self._iac_verb in (251, 253) and self.sock is not None:
                    reply = 254 if self._iac_verb == 251 else 252
                    self.sock.sendall(bytes((255, reply, value)))
                self._iac_state = 0
            elif self._iac_state == 3:
                if value == 255:
                    self._iac_state = 4
            elif self._iac_state == 4:
                self._iac_state = 0 if value == 240 else 3
        return bytes(plain)

    def _read(self, milliseconds: int) -> str:
        if self.sock is None:
            raise GatewayError("Telnet disconnected.")
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            readable, _, _ = select.select([self.sock], [], [], 0.05)
            if not readable:
                continue
            raw = self.sock.recv(8192)
            if not raw:
                raise GatewayError("Telnet disconnected.")
            plain = self._plain_data(raw)
            if plain:
                return self._decoder.decode(plain, final=False)
        return ""

    def open(self, address: str, port: int, password: str, timeout: int = 15) -> None:
        self.close()
        self.sock = socket.create_connection((address, port), timeout=timeout)
        self.sock.setblocking(True)
        self.sock.settimeout(None)
        deadline = time.monotonic() + timeout
        text = ""
        login = 0
        try:
            while time.monotonic() < deadline:
                text += self._read(300)
                if re.search(r"(?:^|[\r\n])[^\r\n]*[#$]\s*$", text):
                    return
                if login == 0 and re.search(r"login:\s*$", text, re.I):
                    self._send("root")
                    login = 1
                    text = ""
                elif login <= 1 and re.search(r"password:\s*$", text, re.I):
                    self._send(password)
                    login = 2
                    text = ""
                if re.search(r"login incorrect|authentication failed", text, re.I):
                    raise GatewayError("Root Telnet login was rejected.")
            raise GatewayError("Telnet login timeout.")
        except Exception:
            self.close()
            raise

    def command(
        self,
        command: str,
        timeout: int = 60,
        progress: Progress | None = None,
    ) -> CommandResult:
        token = f"__GW2_{uuid.uuid4().hex}"
        self._send(command)
        self._send(f"printf '\\n{token}:%s\\n' \"$?\"")
        marker = re.compile(
            rf"(?:^|[\r\n]){re.escape(token)}:([0-9]+)(?:\r?\n)"
        )
        deadline = time.monotonic() + timeout
        output = ""
        while time.monotonic() < deadline:
            chunk = self._read(400)
            if not chunk:
                continue
            output += chunk
            if progress:
                progress(chunk)
            match = marker.search(output)
            if match:
                return CommandResult(int(match.group(1)), output)
            if len(output) > 4 * 1024 * 1024:
                output = output[-2 * 1024 * 1024 :]
        raise GatewayError("Gateway command timed out.")


class _FTPHandler(socketserver.StreamRequestHandler):
    passive: socket.socket | None = None

    def _reply(self, text: str) -> None:
        self.wfile.write((text + "\r\n").encode("ascii"))
        self.wfile.flush()

    def _file_name(self, argument: str) -> Path | None:
        name = urllib.parse.unquote(argument).lstrip("/")
        if "/" in name or "\\" in name or name == "..":
            return None
        return self.server.files.get(name)  # type: ignore[attr-defined]

    def _close_passive(self) -> None:
        if self.passive is not None:
            try:
                self.passive.close()
            except OSError:
                pass
        self.passive = None

    def setup(self) -> None:
        super().setup()
        self.passive = None

    def finish(self) -> None:
        self._close_passive()
        super().finish()

    def handle(self) -> None:
        self._reply("220 GW2 temporary read-only FTP")
        user_ok = False
        authenticated = False
        while True:
            raw = self.rfile.readline(65536)
            if not raw:
                return
            line = raw.decode("ascii", errors="replace").rstrip("\r\n")
            verb, _, argument = line.partition(" ")
            verb = verb.upper()
            if verb == "QUIT":
                self._reply("221 Bye")
                return
            if verb == "USER":
                user_ok = argument == "deploy"
                self._reply("331 Password required" if user_ok else "530 Login rejected")
                continue
            if verb == "PASS":
                authenticated = user_ok and argument == self.server.password  # type: ignore[attr-defined]
                self._reply("230 Logged in" if authenticated else "530 Login rejected")
                continue
            if not authenticated:
                self._reply("530 Login first")
                continue
            if verb == "SYST":
                self._reply("215 UNIX Type: L8")
            elif verb in ("PWD", "XPWD"):
                self._reply('257 "/"')
            elif verb == "CWD":
                self._reply("250 Directory selected" if argument in ("/", ".") else "550 Directory not available")
            elif verb in ("TYPE", "OPTS", "NOOP", "STRU", "MODE"):
                self._reply("200 OK")
            elif verb == "FEAT":
                self._reply("211-Features")
                self._reply(" SIZE")
                self._reply(" EPSV")
                self._reply("211 End")
            elif verb == "SIZE":
                path = self._file_name(argument)
                self._reply(f"213 {path.stat().st_size}" if path else "550 File not available")
            elif verb in ("PASV", "EPSV"):
                self._close_passive()
                passive = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                passive.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                passive.bind((self.server.passive_ip, 21222))  # type: ignore[attr-defined]
                passive.listen(1)
                self.passive = passive
                if verb == "EPSV":
                    self._reply("229 Entering Extended Passive Mode (|||21222|)")
                else:
                    ip = self.server.passive_ip.replace(".", ",")  # type: ignore[attr-defined]
                    self._reply(f"227 Entering Passive Mode ({ip},82,230)")
            elif verb == "RETR":
                path = self._file_name(argument)
                if path is None:
                    self._reply("550 File not available")
                    continue
                if self.passive is None:
                    self._reply("425 Use passive mode")
                    continue
                self._reply("150 Opening binary data connection")
                try:
                    conn, _ = self.passive.accept()
                    with conn, path.open("rb") as source:
                        while block := source.read(32768):
                            conn.sendall(block)
                    self._reply("226 Transfer complete")
                except OSError:
                    self._reply("426 Transfer failed")
                finally:
                    self._close_passive()
            else:
                self._reply("502 Command not supported")


class ReadOnlyFTPServer:
    def __init__(self, local_ip: str, password: str, files: dict[str, Path]) -> None:
        self.server = socketserver.ThreadingTCPServer(
            (local_ip, 21221), _FTPHandler, bind_and_activate=False
        )
        self.server.allow_reuse_address = True
        self.server.daemon_threads = True
        self.server.files = files  # type: ignore[attr-defined]
        self.server.password = password  # type: ignore[attr-defined]
        self.server.passive_ip = local_ip  # type: ignore[attr-defined]
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "ReadOnlyFTPServer":
        self.server.server_bind()
        self.server.server_activate()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)


class TemporaryFirewall:
    def __init__(self, local_ip: str, remote_ip: str) -> None:
        self.name = f"MiGW2-Python-{uuid.uuid4().hex}"
        self.local_ip = local_ip
        self.remote_ip = remote_ip

    @staticmethod
    def _run(args: list[str]) -> None:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise GatewayError(result.stderr.strip() or result.stdout.strip() or "Firewall command failed.")

    def add(self) -> None:
        netsh = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "netsh.exe")
        self._run(
            [
                netsh,
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={self.name}",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localip={self.local_ip}",
                "localport=21221-21222",
                f"remoteip={self.remote_ip}",
                "profile=any",
            ]
        )

    def remove(self) -> None:
        netsh = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "netsh.exe")
        try:
            self._run(
                [
                    netsh,
                    "advfirewall",
                    "firewall",
                    "delete",
                    "rule",
                    f"name={self.name}",
                ]
            )
        except Exception:
            pass


def local_ip_towards(address: str, port: int) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((address, port))
        return sock.getsockname()[0]


def ftp_secret() -> str:
    return secrets.token_hex(16)
