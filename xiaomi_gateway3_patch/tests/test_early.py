"""Exercise real Python import interception, including late-install refusal."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1] / "ha/custom_components/xiaomi_gateway3_telnet_patch"


class EarlyTests(unittest.TestCase):
    def run_case(self, late, version="4.3.0"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["custom_components", "custom_components/xiaomi_gateway3", "custom_components/xiaomi_gateway3/core", "custom_components/xiaomi_gateway3/core/shell"]:
                p = root / name
                p.mkdir(parents=True, exist_ok=True)
                (p / "__init__.py").write_text("")
            (root / "custom_components/xiaomi_gateway3/core/mini_miio.py").write_text("class BasemiIO:\n def _pack_raw(self, msg_id, method, params=None):\n  return params\nclass AsyncMiIO(BasemiIO):\n async def send(self, method, params=None, tries=3):\n  return params\n")
            (root / "custom_components/xiaomi_gateway3/core/core_utils.py").write_text("TELNET_CMD = 'passwd -d $USER; riu_w 101e 53 3012 || echo enable > /sys/class/tty/tty/enable; telnetd'\n")
            (root / "custom_components/xiaomi_gateway3/manifest.json").write_text('{"version":' + repr(version).replace("'", '"') + '}')
            marker = root / "upstream-executed"
            if version != "4.3.0":
                (root / "custom_components/xiaomi_gateway3/__init__.py").write_text(f"open({str(marker)!r}, 'w').write('executed')\n")
            (root / "custom_components/xiaomi_gateway3/core/shell/shell_mgw2.py").write_text("class ShellMGW2:\n async def login(self):\n  return 'original'\n")
            code = f"""
import importlib,sys,types
sys.path.insert(0,{str(root)!r})
package=types.ModuleType('test_patch'); package.__path__=[{str(CODE)!r}];sys.modules['test_patch']=package
from test_patch.early import install_early_hooks
from test_patch.runtime import MANAGER
late={late!r}
if {version!r} != '4.3.0':
 install_early_hooks()
 try: importlib.import_module('custom_components.xiaomi_gateway3.core.mini_miio')
 except ImportError: pass
 else: raise AssertionError('Unreviewed upstream accepted')
 from pathlib import Path
 assert not Path({str(marker)!r}).exists(), 'Upstream code ran before version rejection'
elif late:
 importlib.import_module('custom_components.xiaomi_gateway3.core.mini_miio')
 try: install_early_hooks()
 except RuntimeError: pass
 else: raise AssertionError('Late installation accepted')
else:
 install_early_hooks();install_early_hooks()
 from custom_components.xiaomi_gateway3.core.mini_miio import AsyncMiIO
 from custom_components.xiaomi_gateway3.core.shell.shell_mgw2 import ShellMGW2
 from custom_components.xiaomi_gateway3.core import core_utils
 assert getattr(AsyncMiIO.send,'_gw2_password_patch',False)
 assert getattr(ShellMGW2.login,'_gw2_password_patch',False)
 assert MANAGER.hooks=={{'miio_send','mgw2_login','telnet_command','miio_packet'}}
 assert 'passwd' not in core_utils.TELNET_CMD
 assert MANAGER.early_installed
"""
            subprocess.run([sys.executable, "-c", code], check=True)

    def test_hooks_present_before_upstream_import_returns(self):
        self.run_case(False)

    def test_late_installation_refused(self):
        self.run_case(True)

    def test_unreviewed_version_refused_before_upstream_code(self):
        self.run_case(False, "9.0.0")


if __name__ == "__main__":
    unittest.main()
