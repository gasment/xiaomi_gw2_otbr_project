"""Install import hooks before XiaomiGateway3 imports; no HA setup/network I/O here."""
from importlib import abc, machinery
import json
from pathlib import Path
import sys

from .runtime import MANAGER, patch_login, patch_miio

TARGETS = {
    "custom_components.xiaomi_gateway3.core.shell.shell_mgw2": patch_login,
    "custom_components.xiaomi_gateway3.core.mini_miio": patch_miio,
}
UPSTREAM = "custom_components.xiaomi_gateway3"


def validate_upstream(spec):
    """Refuse an unreviewed module layout/version before upstream code executes."""
    try:
        root = Path(spec.origin).parent
        version = json.loads((root / "manifest.json").read_text())["version"]
        if version != "4.3.0" or not all((root / name).is_file() for name in (
            "core/mini_miio.py", "core/shell/shell_mgw2.py")):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ImportError("Gateway password patch supports reviewed XiaomiGateway3 4.3.0 only; review compatibility before upgrading") from None


class _Loader(abc.Loader):
    def __init__(self, original, callback, before=False):
        self.original = original
        self.callback = callback
        self.before = before

    def create_module(self, spec):
        create = getattr(self.original, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        if self.before:
            self.callback(module.__spec__)
        self.original.exec_module(module)
        if not self.before:
            self.callback(module)


class _Finder(abc.MetaPathFinder):
    _gw2_password_hook = True

    def find_spec(self, fullname, path=None, target=None):
        callback = validate_upstream if fullname == UPSTREAM else TARGETS.get(fullname)
        if callback is None:
            return None
        spec = machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None:
            raise ImportError("XiaomiGateway3 password patch cannot locate upstream module")
        spec.loader = _Loader(spec.loader, callback, before=fullname == UPSTREAM)
        return spec


def install_early_hooks():
    """Called by custom_components/__init__.py before importing child packages."""
    if any(getattr(finder, "_gw2_password_hook", False) for finder in sys.meta_path):
        return
    if any(name in sys.modules for name in (*TARGETS, UPSTREAM)):
        raise RuntimeError("Password hook loaded too late; install bootstrap and restart HA")
    sys.meta_path.insert(0, _Finder())
    MANAGER.early_installed = True
