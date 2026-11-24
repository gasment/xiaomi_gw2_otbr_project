"""Pure-Python and loopback tests; no Home Assistant instance or gateway required."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "ha/custom_components/xiaomi_gateway3_telnet_patch"
spec = importlib.util.spec_from_file_location("gw2_patch_runtime_test", CODE / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def miio_class():
    class MiIO:
        def __init__(self, host="127.0.0.1"):
            self.addr = (host, 54321)
            self.calls = []

        async def send(self, method, params=None, tries=3):
            self.calls.append((method, params, tries))
            return {"result": ["ok"]}
    runtime.patch_miio(types.SimpleNamespace(AsyncMiIO=MiIO))
    return MiIO


def shell_class():
    class E1:
        async def login(self):
            self.legacy = True
    class GW2(E1):
        pass
    runtime.patch_login(types.SimpleNamespace(ShellMGW2=GW2))
    return GW2, E1


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime.MANAGER = runtime.Manager()

    def configure(self):
        runtime.MANAGER.configure({"127.0.0.1": {"password": "fixture-password"}})

    async def test_original_delete_command_is_sanitized_without_mutating_params(self):
        self.configure()
        obj = miio_class()()
        params = {"password": "miio-proof", "command": runtime.ORIGINAL_TELNET_COMMAND}
        await obj.send("system_command", params, tries=1)
        self.assertEqual(obj.calls[0], ("system_command", {"password": "miio-proof", "command": runtime.SAFE_TELNET_COMMAND}, 1))
        self.assertEqual(params["command"], runtime.ORIGINAL_TELNET_COMMAND)

    async def test_set_ip_info_delete_removed(self):
        self.configure()
        obj = miio_class()()
        await obj.send("set_ip_info", {"ssid": '""', "pswd": "1; " + runtime.ORIGINAL_TELNET_COMMAND})
        self.assertEqual(obj.calls[0][1]["pswd"], "1; " + runtime.SAFE_TELNET_COMMAND)

    async def test_unknown_privileged_commands_and_legacy_builtin_blocked(self):
        self.configure()
        obj = miio_class()()
        for command in ["passwd -d root", "busybox passwd --delete root", "pass'w'd -d root", "echo arbitrary"]:
            with self.assertRaises(runtime.PasswordPatchError):
                await obj.send("system_command", {"command": command})
        with self.assertRaises(runtime.PasswordPatchError):
            await obj.send("enable_telnet_service")
        with self.assertRaises(runtime.PasswordPatchError):
            await obj.send("set_ip_info", {"pswd": "1; passwd -d root"})
        self.assertEqual(obj.calls, [])

    async def test_unmatched_host_still_cannot_delete_password(self):
        self.configure()
        obj = miio_class()("127.0.0.2")
        await obj.send("system_command", {"command": runtime.ORIGINAL_TELNET_COMMAND})
        self.assertEqual(obj.calls[0][1]["command"], runtime.SAFE_TELNET_COMMAND)

    async def test_delete_removed_before_configuration_is_loaded(self):
        obj = miio_class()()
        await asyncio.wait_for(obj.send("system_command", {"command": runtime.ORIGINAL_TELNET_COMMAND}),1)
        self.assertNotIn("passwd", obj.calls[0][1]["command"])

    async def test_empty_config_and_partial_two_gateway_config_never_release_delete(self):
        cls = miio_class()
        for gateways in ({}, {"127.0.0.2": {"password": "second-fixture"}}):
            runtime.MANAGER.configure(gateways, allow_empty=True)
            first,second = cls("127.0.0.1"),cls("127.0.0.2")
            await asyncio.gather(first.send("system_command", {"command": runtime.ORIGINAL_TELNET_COMMAND}),
                                 second.send("set_ip_info", {"pswd": "1; " + runtime.ORIGINAL_TELNET_COMMAND}))
            self.assertNotIn("passwd", first.calls[0][1]["command"])
            self.assertNotIn("passwd", second.calls[0][1]["pswd"])

    async def test_builtin_reset_blocked_before_configuration(self):
        obj=miio_class()()
        with self.assertRaises(runtime.PasswordPatchError):
            await asyncio.wait_for(obj.send("enable_telnet_service"),1)
        self.assertEqual(obj.calls,[])

    def test_core_utils_constant_guard(self):
        module=types.SimpleNamespace(TELNET_CMD=runtime.ORIGINAL_TELNET_COMMAND)
        runtime.patch_telnet_command(module)
        runtime.patch_telnet_command(module)
        self.assertEqual(module.TELNET_CMD,runtime.SAFE_TELNET_COMMAND)
        with self.assertRaises(ImportError):
            runtime.patch_telnet_command(types.SimpleNamespace(TELNET_CMD="changed"))

    async def test_packet_boundary_protects_sync_and_saved_async_send(self):
        class Base:
            addr=("127.0.0.1",54321)
            def _pack_raw(self,msg_id,method,params=None):
                return params
        class Async(Base):
            async def send(self,method,params=None,tries=3):
                return self._pack_raw(1,method,params)
        class Sync(Base):
            def send(self,method,params=None):
                return self._pack_raw(2,method,params)
        obj=Async()
        saved_send=obj.send  # Bound before the high-level wrapper is installed.
        module=types.SimpleNamespace(BasemiIO=Base,AsyncMiIO=Async,SyncMiIO=Sync)
        runtime.patch_miio_module(module)
        runtime.patch_miio_module(module)
        params={"command":runtime.ORIGINAL_TELNET_COMMAND,"password":"fixture-miio-proof"}
        with self.assertLogs(runtime.LOGGER,level="WARNING") as captured:
            first=await saved_send("system_command",params)
            second=Sync().send("system_command",params)
        self.assertEqual(first["command"],runtime.SAFE_TELNET_COMMAND)
        self.assertEqual(second["command"],runtime.SAFE_TELNET_COMMAND)
        self.assertEqual(params["command"],runtime.ORIGINAL_TELNET_COMMAND)
        self.assertNotIn("fixture-miio-proof","\n".join(captured.output))
        for client in (obj,Sync()):
            with self.assertRaises(runtime.PasswordPatchError):
                client._pack_raw(3,"enable_telnet_service")
            with self.assertRaises(runtime.PasswordPatchError):
                client._pack_raw(4,"system_command",{"command":"passwd -d root"})
        untouched={"any":"value"}
        self.assertIs(obj._pack_raw(5,"miIO.info",untouched),untouched)

    def test_packet_set_ip_info_guard_and_api_validation(self):
        class Base:
            addr=("127.0.0.1",54321)
            def _pack_raw(self,msg_id,method,params=None):return params
        runtime.patch_packet_transport(types.SimpleNamespace(BasemiIO=Base))
        params={"pswd":"1; "+runtime.ORIGINAL_TELNET_COMMAND,"ssid":'""'}
        result=Base()._pack_raw(1,"set_ip_info",params)
        self.assertEqual(result["pswd"],"1; "+runtime.SAFE_TELNET_COMMAND)
        self.assertEqual(params["pswd"],"1; "+runtime.ORIGINAL_TELNET_COMMAND)
        with self.assertRaises(runtime.PasswordPatchError):Base()._pack_raw(2,"set_ip_info",None)
        class Changed:
            def _pack_raw(self,extra):pass
        with self.assertRaises(ImportError):runtime.patch_packet_transport(types.SimpleNamespace(BasemiIO=Changed))

    async def test_ordinary_miio_info_does_not_wait_for_patch_config(self):
        obj = miio_class()()
        await asyncio.wait_for(obj.send("miIO.info"), 1)
        self.assertEqual(obj.calls[0][0], "miIO.info")

    async def exercise_login(self, mode):
        self.configure()
        received = []
        complete = asyncio.Event()

        async def server(reader, writer):
            try:
                writer.write(b"Mijia_Hub_V2-TEST login: ")
                await writer.drain()
                received.append(await reader.readline())
                if mode == "empty":
                    writer.write(b"\r\n~ # ")
                else:
                    writer.write(b"Pass")
                    await writer.drain()
                    await asyncio.sleep(0)
                    writer.write(b"word: ")
                    await writer.drain()
                    received.append(await reader.readline())
                    writer.write(b"\r\n~ # " if mode == "good" else b"\r\nLogin incorrect\r\nlogin: ")
                await writer.drain()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
                complete.set()

        listener = await asyncio.start_server(server, "127.0.0.1", 0)
        reader, writer = await asyncio.open_connection("127.0.0.1", listener.sockets[0].getsockname()[1])
        try:
            # The upstream Session consumes the banner before invoking ShellMGW2.login.
            await reader.readuntil(b"login: ")
            cls, e1 = shell_class()
            shell = cls()
            shell.reader, shell.writer = reader, writer
            self.assertFalse(getattr(e1.login, "_gw2_password_patch", False))
            if mode == "good":
                await shell.login()
            else:
                with self.assertRaises(runtime.PasswordPatchError):
                    await shell.login()
        finally:
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(complete.wait(), 2)
            listener.close()
            await listener.wait_closed()
        return received

    async def test_telnet_password_login(self):
        self.assertEqual(await self.exercise_login("good"), [b"root\n", b"fixture-password\n"])

    async def test_wrong_password_never_retries_empty(self):
        self.assertEqual(await self.exercise_login("wrong"), [b"root\n", b"fixture-password\n"])

    async def test_empty_password_gateway_rejected(self):
        self.assertEqual(await self.exercise_login("empty"), [b"root\n"])

    async def test_incompatible_api_rejected(self):
        class Changed:
            async def send(self, extra):
                pass
        with self.assertRaises(ImportError):
            runtime.patch_miio(types.SimpleNamespace(AsyncMiIO=Changed))


if __name__ == "__main__":
    unittest.main()
