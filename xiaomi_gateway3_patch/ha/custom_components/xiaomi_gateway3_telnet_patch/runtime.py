"""Password-aware MGW2 login and configuration-independent deletion guard."""
import asyncio
from functools import wraps
import inspect
import ipaddress
import logging
import re

LOGGER = logging.getLogger("custom_components.xiaomi_gateway3_telnet_patch")
ORIGINAL_TELNET_COMMAND = "passwd -d $USER; riu_w 101e 53 3012 || echo enable > /sys/class/tty/tty/enable; telnetd"
SAFE_TELNET_COMMAND = ORIGINAL_TELNET_COMMAND.split("; ", 1)[1]


class PasswordPatchError(RuntimeError):
    """Intentionally carries no credentials or upstream parameters."""


class Manager:
    def __init__(self):
        self.early_installed = False
        self.hooks = set()
        self._passwords = None
        self._ready = None
        self._retired = set()

    def configure(self, gateways, *, allow_empty=False):
        passwords = {}
        for host, options in gateways.items():
            try:
                address = str(ipaddress.ip_address(host))
            except ValueError:
                raise PasswordPatchError("Gateway host must be an IPv4/IPv6 address") from None
            password = options["password"]
            if not isinstance(password, str) or not password or len(password.encode()) > 256:
                raise PasswordPatchError("A nonempty password of at most 256 UTF-8 bytes is required")
            if any(ord(c) < 32 or ord(c) == 127 for c in password):
                raise PasswordPatchError("Password must not contain control characters")
            passwords[address] = password
        if not passwords and not allow_empty:
            raise PasswordPatchError("Configure at least one protected gateway")
        if self._passwords is not None:
            self._retired.update(self._passwords.keys() - passwords.keys())
        self._retired.difference_update(passwords)
        self._passwords = passwords
        if self._ready is not None:
            self._ready.set()

    async def password_for(self, host):
        if self._passwords is None:
            if self._ready is None:
                self._ready = asyncio.Event()
            try:
                await asyncio.wait_for(self._ready.wait(), 30)
            except TimeoutError:
                raise PasswordPatchError("Password patch configuration not ready; operation blocked") from None
        try:
            host = str(ipaddress.ip_address(host))
        except ValueError:
            raise PasswordPatchError("Cannot identify gateway address; operation blocked") from None
        if host in self._retired:
            raise PasswordPatchError("Gateway protection was removed; legacy password reset stays blocked until restart")
        return self._passwords.get(host)


MANAGER = Manager()


def patch_telnet_command(module):
    """Protect the audited enable command before any HA entry is set up."""
    command = getattr(module, "TELNET_CMD", None)
    if command not in (ORIGINAL_TELNET_COMMAND, SAFE_TELNET_COMMAND):
        raise ImportError("Unsupported XiaomiGateway3 Telnet command; password guard refused")
    module.TELNET_CMD = SAFE_TELNET_COMMAND
    MANAGER.hooks.add("telnet_command")
    LOGGER.warning("GW2_PASSWORD_PATCH_COMMAND_GUARD_ACTIVE: password deletion removed from upstream Telnet enable command")


def sanitize_command(command):
    """Recognize the audited upstream command, reject other passwd operations."""
    if command == ORIGINAL_TELNET_COMMAND:
        return SAFE_TELNET_COMMAND
    if command == SAFE_TELNET_COMMAND:
        return command
    raise PasswordPatchError("Unrecognized privileged command blocked; review upstream compatibility")


async def _read_login_stage(reader, timeout=8):
    async def read():
        data = bytearray()
        while len(data) <= 8192:
            chunk = await reader.read(512)
            if not chunk:
                raise PasswordPatchError("Telnet connection closed during authentication")
            data.extend(chunk)
            lower = bytes(data).lower()
            if any(x in lower for x in (b"login incorrect", b"authentication failed", b"access denied")):
                raise PasswordPatchError("Telnet authentication rejected")
            if re.search(rb"password:\s*$", lower):
                return "password"
            if re.search(rb"(?:^|[\r\n])[^\r\n]* # $", bytes(data)):
                return "shell"
            if re.search(rb"login:\s*$", lower):
                raise PasswordPatchError("Telnet returned to login prompt")
        raise PasswordPatchError("Unexpected Telnet authentication response")
    try:
        return await asyncio.wait_for(read(), timeout)
    except TimeoutError:
        raise PasswordPatchError("Telnet authentication timed out") from None


def patch_login(module):
    cls = module.ShellMGW2
    original = cls.login
    if getattr(original, "_gw2_password_patch", False):
        return
    if not inspect.iscoroutinefunction(original) or tuple(inspect.signature(original).parameters) != ("self",):
        raise ImportError("Unsupported XiaomiGateway3 MGW2 login API; password patch refused")

    @wraps(original)
    async def login(self):
        try:
            peer = self.writer.get_extra_info("peername")
            if not peer:
                raise PasswordPatchError("Cannot identify Telnet peer")
            password = await MANAGER.password_for(peer[0])
            if password is None:
                return await original(self)
            self.writer.write(b"root\n")
            await self.writer.drain()
            if await _read_login_stage(self.reader) != "password":
                raise PasswordPatchError("Protected gateway accepted empty-password root; set its password first")
            self.writer.write(password.encode("utf-8") + b"\n")
            await self.writer.drain()
            if await _read_login_stage(self.reader) != "shell":
                raise PasswordPatchError("Telnet authentication rejected")
        except BaseException:
            self.writer.close()
            raise

    login._gw2_password_patch = True
    cls.login = login
    MANAGER.hooks.add("mgw2_login")


def patch_packet_transport(module):
    """Guard the shared serializer used by both SyncMiIO and AsyncMiIO."""
    base = module.BasemiIO
    original = base._pack_raw
    if getattr(original, "_gw2_password_patch", False):
        return
    if inspect.iscoroutinefunction(original) or tuple(inspect.signature(original).parameters) != ("self", "msg_id", "method", "params"):
        raise ImportError("Unsupported XiaomiGateway3 miIO packet API; password guard refused")

    @wraps(original)
    def pack(self, msg_id, method, params=None):
        if method == "enable_telnet_service":
            raise PasswordPatchError("Built-in Telnet reset blocked at packet boundary")
        if method in ("system_command", "set_ip_info"):
            if not isinstance(params, dict):
                raise PasswordPatchError("Unknown privileged packet parameters blocked")
            params = dict(params)
            if method == "system_command":
                params["command"] = sanitize_command(params.get("command"))
            else:
                command = params.get("pswd")
                if command not in ("1; " + ORIGINAL_TELNET_COMMAND, "1; " + SAFE_TELNET_COMMAND):
                    raise PasswordPatchError("Unrecognized privileged packet blocked")
                params["pswd"] = "1; " + SAFE_TELNET_COMMAND
            try:
                host = str(ipaddress.ip_address(self.addr[0]))
            except (ValueError, AttributeError, TypeError, IndexError):
                host = "unresolved"
            LOGGER.warning("GW2_PASSWORD_PATCH_TELNET_ENABLE_PACKED: gateway=%s method=%s transport=%s command=safe",
                           host, method, "async" if inspect.iscoroutinefunction(getattr(self, "send", None)) else "sync")
        return original(self, msg_id, method, params)

    pack._gw2_password_patch = True
    base._pack_raw = pack
    MANAGER.hooks.add("miio_packet")
    LOGGER.warning("GW2_PASSWORD_PATCH_PACKET_GUARD_ACTIVE: shared SyncMiIO/AsyncMiIO serializer protected")


def patch_miio_module(module):
    patch_packet_transport(module)
    patch_miio(module)


def patch_miio(module):
    original = module.AsyncMiIO.send
    if getattr(original, "_gw2_password_patch", False):
        return
    if not inspect.iscoroutinefunction(original) or tuple(inspect.signature(original).parameters) != ("self", "method", "params", "tries"):
        raise ImportError("Unsupported XiaomiGateway3 miIO API; password patch refused")

    @wraps(original)
    async def send(self, method, params=None, tries=3):
        # This guard is intentionally independent of credentials and entry
        # setup order. Never release the audited deletion command, even when
        # configuration is empty, incomplete, or the host is not matched.
        if method == "enable_telnet_service":
            raise PasswordPatchError("Built-in Telnet enable can clear passwords; operation blocked")
        if method == "system_command" and isinstance(params, dict):
            command = params.get("command")
            if command in (ORIGINAL_TELNET_COMMAND, SAFE_TELNET_COMMAND):
                safe = dict(params)
                safe["command"] = SAFE_TELNET_COMMAND
                if command == ORIGINAL_TELNET_COMMAND:
                    LOGGER.warning("GW2_PASSWORD_PATCH_DELETE_STRIPPED: system_command")
                return await original(self, method, safe, tries)
        if method == "set_ip_info" and isinstance(params, dict):
            command = params.get("pswd")
            if command in ("1; " + ORIGINAL_TELNET_COMMAND, "1; " + SAFE_TELNET_COMMAND):
                safe = dict(params)
                safe["pswd"] = "1; " + SAFE_TELNET_COMMAND
                if command == "1; " + ORIGINAL_TELNET_COMMAND:
                    LOGGER.warning("GW2_PASSWORD_PATCH_DELETE_STRIPPED: set_ip_info")
                return await original(self, method, safe, tries)
        if method in ("system_command", "set_ip_info", "enable_telnet_service"):
            password = await MANAGER.password_for(self.addr[0])
            if password is not None:
                if method == "enable_telnet_service":
                    raise PasswordPatchError("Legacy built-in Telnet enable blocked for protected gateway")
                if not isinstance(params, dict):
                    raise PasswordPatchError("Unknown privileged miIO parameters blocked")
                params = dict(params)
                if method == "system_command":
                    command = params.get("command")
                    if not isinstance(command, str):
                        raise PasswordPatchError("Unknown system_command payload blocked")
                    params["command"] = sanitize_command(command)
                else:
                    command = params.get("pswd")
                    if isinstance(command, str):
                        prefix = "1; "
                        if command == prefix + ORIGINAL_TELNET_COMMAND:
                            params["pswd"] = prefix + SAFE_TELNET_COMMAND
                        elif command != prefix + SAFE_TELNET_COMMAND:
                            raise PasswordPatchError("Unrecognized Telnet enable payload blocked")
                    else:
                        raise PasswordPatchError("Unknown Telnet enable payload blocked")
        return await original(self, method, params, tries)

    send._gw2_password_patch = True
    module.AsyncMiIO.send = send
    MANAGER.hooks.add("miio_send")
