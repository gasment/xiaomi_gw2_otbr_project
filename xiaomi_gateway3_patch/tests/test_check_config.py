import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

CODE=Path(__file__).resolve().parents[1]/"ha/custom_components/xiaomi_gateway3_telnet_patch/check_config.py"
spec=importlib.util.spec_from_file_location("check_patch_disk",CODE)
check=importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class DiskCheckTests(unittest.TestCase):
    def fixture(self, root, missing=False):
        custom=root/"custom_components"
        (custom/"xiaomi_gateway3").mkdir(parents=True)
        (custom/"__init__.py").write_text("from .xiaomi_gateway3_telnet_patch.early import install_early_hooks as setup_guard\nsetup_guard()\n")
        (custom/"xiaomi_gateway3/manifest.json").write_text('{"version":"4.3.0"}')
        (root/".storage").mkdir()
        entries=[]
        for host in ("192.0.2.10","192.0.2.11"):
            entries.append({"domain":"xiaomi_gateway3","data":{"token":"secret-token"},"options":{"host":host}})
            if not(missing and host.endswith(".10")):
                entries.append({"domain":"xiaomi_gateway3_telnet_patch","data":{"host":host,"password":"secret-password"}})
        (root/".storage/core.config_entries").write_text(json.dumps({"data":{"entries":entries}}))

    def test_two_hosts_and_no_credentials_in_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);out=io.StringIO()
            with contextlib.redirect_stdout(out): result=check.inspect_config(root)
            self.assertEqual(result,0)
            self.assertEqual(out.getvalue().count("password_login_config=matched"),2)
            self.assertNotIn("secret-password",out.getvalue())
            self.assertNotIn("secret-token",out.getvalue())

    def test_missing_one_host_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root,True);out=io.StringIO()
            with contextlib.redirect_stdout(out): result=check.inspect_config(root)
            self.assertEqual(result,1)
            self.assertIn("GATEWAY host=192.0.2.10 password_login_config=missing",out.getvalue())

    def test_missing_bootstrap_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            (root/"custom_components/__init__.py").write_text("# no hook\n")
            out=io.StringIO()
            with contextlib.redirect_stdout(out):result=check.inspect_config(root)
            self.assertEqual(result,1)
            self.assertIn("BOOTSTRAP_ON_DISK=missing_or_invalid",out.getvalue())
