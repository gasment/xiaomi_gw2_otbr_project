"""Real voluptuous schemas with mocked HA flow/lifecycle contracts; no live HA."""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

HAS_VOL = importlib.util.find_spec("voluptuous") is not None
CODE = Path(__file__).resolve().parents[1] / "ha/custom_components/xiaomi_gateway3_telnet_patch"


@unittest.skipUnless(HAS_VOL, "Install voluptuous for UI contract tests; HA already includes it")
class UIFlowTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import voluptuous as vol
        class Flow:
            def __init_subclass__(cls, **kwargs):
                return super().__init_subclass__()
            async def async_set_unique_id(self, value):
                self.unique_id = value
            def _abort_if_unique_id_configured(self):
                pass
            def async_abort(self, **kwargs):
                return {"type": "abort", **kwargs}
            def async_create_entry(self, **kwargs):
                return {"type": "create_entry", **kwargs}
            def async_show_form(self, **kwargs):
                return {"type": "form", **kwargs}
        class TextSelector:
            def __init__(self, config):
                self.config = config
            def __call__(self, value):
                if not isinstance(value, str):
                    raise vol.Invalid("string required")
                return value
        class NotReady(Exception):
            pass
        ha = types.ModuleType("homeassistant")
        ha.__path__ = []
        helpers = types.ModuleType("homeassistant.helpers")
        helpers.__path__ = []
        modules = {
            "homeassistant": ha, "homeassistant.helpers": helpers,
            "homeassistant.config_entries": types.SimpleNamespace(ConfigFlow=Flow, OptionsFlow=Flow),
            "homeassistant.core": types.SimpleNamespace(callback=lambda f: f),
            "homeassistant.exceptions": types.SimpleNamespace(ConfigEntryNotReady=NotReady),
            "homeassistant.helpers.config_validation": types.SimpleNamespace(string=str),
            "homeassistant.helpers.selector": types.SimpleNamespace(TextSelector=TextSelector, TextSelectorConfig=dict, TextSelectorType=types.SimpleNamespace(PASSWORD="password")),
            "homeassistant.helpers.issue_registry": types.SimpleNamespace(async_create_issue=lambda *a, **k: None, async_delete_issue=lambda *a, **k: None, IssueSeverity=types.SimpleNamespace(WARNING="warning")),
        }
        sys.modules.update(modules)
        cls.NotReady = NotReady
        spec = importlib.util.spec_from_file_location("gw2_ui_test", CODE / "__init__.py", submodule_search_locations=[str(CODE)])
        cls.component = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.component
        spec.loader.exec_module(cls.component)
        cls.flow = importlib.import_module("gw2_ui_test.config_flow")
        cls.runtime = importlib.import_module("gw2_ui_test.runtime")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        (base / "custom_components").mkdir()
        self.entries = []
        class Entries:
            def __init__(self, items): self.items = items
            def async_entries(self, domain): return self.items
            def async_update_entry(self, entry, **kwargs):
                for key, value in kwargs.items(): setattr(entry, key, value)
        async def executor(function, *args): return await asyncio.to_thread(function, *args)
        self.hass = types.SimpleNamespace(data={}, config_entries=Entries(self.entries),
            config=types.SimpleNamespace(path=lambda *parts: str(base.joinpath(*parts))), async_add_executor_job=executor)
        manager = self.runtime.Manager()
        self.component.MANAGER = self.flow.MANAGER = self.runtime.MANAGER = manager

    def entry(self, host="192.0.2.10", password="fixture-password", entry_id="a"):
        return types.SimpleNamespace(entry_id=entry_id, data={"host": host, "password": password},
            async_on_unload=lambda callback: None, add_update_listener=lambda callback: lambda: None)

    def config_flow(self):
        flow = self.flow.PasswordConfigFlow()
        flow.hass = self.hass
        return flow

    async def test_ui_creation_installs_bootstrap_without_yaml(self):
        result = await self.config_flow().async_step_user({"host": "192.0.2.10", "password": "fixture-password", "install_bootstrap": True})
        self.assertEqual(result["type"], "create_entry")
        self.assertTrue((Path(self.directory.name) / "custom_components/__init__.py").exists())

    async def test_password_not_prefilled_on_invalid_input(self):
        result = await self.config_flow().async_step_user({"host": "bad", "password": "do-not-echo", "install_bootstrap": True})
        self.assertEqual(result["errors"]["base"], "invalid_host")
        self.assertNotIn("do-not-echo", repr(result))

    async def test_duplicate_host_aborts(self):
        self.entries.append(self.entry())
        result = await self.config_flow().async_step_user({"host": "192.0.2.10", "password": "fixture", "install_bootstrap": True})
        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})

    async def test_empty_password_refused(self):
        result = await self.config_flow().async_step_user({"host": "192.0.2.10", "password": "", "install_bootstrap": True})
        self.assertEqual(result["errors"]["base"], "invalid_password")

    async def test_bootstrap_failure_does_not_create_entry(self):
        p = Path(self.directory.name) / "custom_components/__init__.py"
        p.write_text("broken (\n")
        result = await self.config_flow().async_step_user({"host": "192.0.2.10", "password": "fixture", "install_bootstrap": True})
        self.assertEqual(result["errors"]["base"], "bootstrap_failed")

    async def test_opt_out_without_active_hook_refused(self):
        result = await self.config_flow().async_step_user({"host": "192.0.2.10", "password": "fixture", "install_bootstrap": False})
        self.assertEqual(result["errors"]["base"], "bootstrap_required")

    async def test_startup_reads_all_ui_credentials_before_entry_setup(self):
        self.entries.extend([self.entry(), self.entry("192.0.2.11", "second-fixture", "b")])
        self.component.MANAGER.early_installed = True
        self.assertTrue(await self.component.async_setup(self.hass, {}))
        self.assertEqual(await self.component.MANAGER.password_for("192.0.2.11"), "second-fixture")

    async def test_first_install_requires_restart_before_entry_ready(self):
        entry = self.entry(); self.entries.append(entry)
        await self.component.async_setup(self.hass, {})
        with self.assertRaises(self.NotReady): await self.component.async_setup_entry(self.hass, entry)

    async def test_options_change_without_exposing_old_password(self):
        entry = self.entry(); self.entries.append(entry)
        await self.component.async_setup(self.hass, {})
        flow = self.flow.PasswordOptionsFlow(); flow.hass = self.hass; flow.config_entry = entry
        result = await flow.async_step_init()
        self.assertNotIn("fixture-password", repr(result))
        result = await flow.async_step_init({"host": "192.0.2.11", "password": "new-fixture"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(await self.component.MANAGER.password_for("192.0.2.11"), "new-fixture")
        with self.assertRaises(self.runtime.PasswordPatchError): await self.component.MANAGER.password_for("192.0.2.10")

    async def test_options_blank_keeps_existing_password(self):
        entry = self.entry(); self.entries.append(entry)
        flow = self.flow.PasswordOptionsFlow(); flow.hass = self.hass; flow.config_entry = entry
        await flow.async_step_init({"host": "192.0.2.10", "password": ""})
        self.assertEqual(entry.data["password"], "fixture-password")


if __name__ == "__main__": unittest.main()
