"""Offline upgrade orchestration with real archives and an isolated RCP-mode installer."""
from contextlib import contextmanager
from importlib import import_module
from itertools import combinations
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parents[3]
ARCHIVED_BASELINE = PROJECT.parent / "dev_archive/mi_gw2_otbr_project_github_0.3.0"
DEFAULT_BASELINE = ARCHIVED_BASELINE if ARCHIVED_BASELINE.is_dir() else PROJECT.with_name("mi_gw2_otbr_project_github")
BASELINE = Path(os.environ.get("GW2_UPGRADE_BASELINE", DEFAULT_BASELINE))
LABELS = {
    "mi_gateway_2_openssh_deploy": "openssh",
    "mi_gateway_2_tun_deploy": "tun",
    "ble-spec-cache": "ble-cache",
    "otbr-deploy": "otbr",
}
STOCK_FW = """#!/bin/sh
coordinator_ota()
{
    :
}
mZ3GatewayHost_MQTT -p /dev/ttyS1
mzigbee_agent -f /etc/mzigbeeAgent.conf
"""
STOCK_MONITOR = """#!/bin/sh
handler_mZ3GatewayHost_MQTT_leaved()
{
    :
}
handler_mzigbee_agent_leaved()
{
    :
}
"""


def engine_modules(directory):
    for name in ("engine", "gateway", "resources", "legacy_versions"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(directory))
    try:
        return import_module("engine"), import_module("resources")
    finally:
        sys.path.pop(0)


def isolated(tree, package, command):
    return subprocess.run(
        ["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--unshare-net",
         "--new-session", "--die-with-parent", "--ro-bind", "/usr", "/usr",
         "--ro-bind", "/etc/alternatives", "/etc/alternatives",
         "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
         "--bind", str(tree / "data"), "/data", "--ro-bind", str(tree / "bin"), "/bin",
         "--ro-bind", str(package), "/pkg", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/pkg",
         "/usr/bin/sh", "-c", command],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=30,
    )


class Offline:
    def __init__(self, module, assets, tree, firmware="2.5.3", confirm=True):
        self.module = module
        self.engine = module.AutoDeployEngine(assets, "offline", 23, "", lambda _: None, lambda *_: confirm)
        self.tree = tree
        self.firmware = firmware
        self.running = False
        self.flash_count = 0
        self.extracts = []
        self.installs = []
        self.events = []
        self.engine.telnet = type("StubTelnet", (), {"connected": True})()
        self.engine.transfer_session = self.transfer
        self.engine.extract = self.extract
        self.engine.install_root = self.install
        self.engine.command = self.command
        self.engine.ensure_openmiio = lambda: self.events.append("shared-openmiio")
        self.engine._reboot_and_verify = lambda *_: None
        self.fail_flash = False

    @contextmanager
    def transfer(self, names):
        for name in names:
            self.engine._asset(name)
        with tempfile.TemporaryDirectory(dir=self.tree, prefix="transfer-") as path:
            self.stage = Path(path)
            self.engine.stage = str(self.stage)
            yield
            self.engine.stage = None

    def extract(self, name, directory):
        file = self.engine._asset(name)
        with tarfile.open(file) as package:
            package.extractall(self.stage, filter="data")
        extracted = self.stage / directory
        subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=extracted, check=True)
        self.extracts.append(name)
        return str(extracted)

    def install(self, directory):
        source = self.stage / directory
        data = self.tree / "data"
        self.installs.append(directory)
        if directory == "ble-spec-cache" and "rcp-openmiio" in self.installs and hasattr(self.engine, "wait_for_clean_openmiio"):
            assert "openmiio-ready" in self.events
        if directory == "post-init-modular":
            state = data / "post-init"
            state.mkdir(exist_ok=True)
            for relative in ("post-initctl.sh", "install-common.sh", "migrate-legacy.sh",
                             "modules/otbr.sh", "modules/openssh.sh", "modules/tun.sh", "modules/ble-cache.sh"):
                target = state / relative
                target.parent.mkdir(exist_ok=True)
                if target.is_file():
                    assert target.read_bytes() == (source / relative).read_bytes(), relative
                else:
                    shutil.copy2(source / relative, target)
        elif directory == "rcp-mode":
            result = isolated(self.tree, source, "sh install.sh")
            if result.returncode:
                raise self.module.GatewayError(result.stdout + result.stderr)
        elif directory == "rcp-openmiio":
            if not getattr(self.engine, "asset_names", {}).get("rcp-openmiio", "").endswith("-0.3.2.tar.gz"):
                shutil.copytree(source / "payload", data / "rcp-openmiio", dirs_exist_ok=True)
            else:
                probe = source / "payload/openmiio-version-check.sh"
                probe.chmod(0o644)
                result = isolated(self.tree, source, "sh install.sh")
                if result.returncode:
                    raise self.module.GatewayError(result.stdout + result.stderr)
                assert "OPENMIIO_VERSION_OK" in result.stdout
                assert (data / "rcp-openmiio/openmiio-version-check.sh").stat().st_mode & 0o100
        elif directory in LABELS:
            label = LABELS[directory]
            dest = data / label
            dest.mkdir(exist_ok=True)
            version = (source / "VERSION").read_text().strip()
            (dest / "observed-version").write_text(version)
            if directory == "otbr-deploy":
                shutil.copytree(source / "payload", dest, dirs_exist_ok=True)
                shutil.copy2(source / "VERSION", dest / "VERSION")
                self.running = True
            env = {
                **os.environ,
                "GW2_POST_INIT_BASE": str(data / "registered"),
                "GW2_POST_INIT_HOOK": str(data / "post_init.sh"),
                "GW2_POST_INIT_LOCK": str(data / "post_init.lock"),
            }
            result = subprocess.run(
                ["sh", str(data / "post-init/post-initctl.sh"), "add", label,
                 str(data / "post-init/modules" / f"{label}.sh")],
                env=env, capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0, result.stderr
        else:
            raise AssertionError(directory)

    def command(self, command, **_kwargs):
        result = ""
        if "OTBR_PAUSED_FOR_UPGRADE" in command:
            if self.running:
                self.running = False
                self.events.append("stop-host")
                result = "OTBR_PAUSED_FOR_UPGRADE"
        elif command.startswith("if [ -f /data/otbr/config.yaml ]"):
            self.events.append("config-preflight")
        elif "echo RCP_FLASH_MARKER_PRESENT" in command:
            result = "RCP_FLASH_MARKER_PRESENT" if self.marker.exists() else "RCP_FLASH_MARKER_ABSENT"
        elif command.startswith("chmod 700 ") and "spinel-probe-" in command:
            name = Path(shlex.split(command)[2].rstrip(";")).name
            probe = self.engine._asset(name)
            if b"SL-OPENTHREAD/3.1.1.0_GitHub-fb274efe6;" in probe.read_bytes():
                expected = "3.1.1/230400"
            elif name.endswith("-0.3.2"):
                expected = "2.5.3/115200"
            else:
                expected = "2.5.3"
            self.events.append("probe")
            if not self.running and self.firmware == expected:
                result = "SPINEL_RCP_PROBE_PASS"
        elif command.startswith("mkdir -p /data/mi-gw2-gui; date"):
            self.marker.touch()
        elif "sh prepare-local.sh && sh flash-rcp.sh" in command:
            if self.running:
                raise self.module.GatewayError("UART busy")
            self.flash_count += 1
            if self.fail_flash:
                raise self.module.GatewayError("simulated serial write failed")
            flash_script = (self.stage / "rcp-native/flash-rcp.sh").read_text()
            if "_115200.gbl" in flash_script:
                self.firmware = "2.5.3/115200"
            elif "_230400.gbl" in flash_script:
                self.firmware = "3.1.1/230400"
            else:
                self.firmware = "2.5.3"
        elif command.startswith("rm -f /data/mi-gw2-gui/rcp-flash-in-progress"):
            self.marker.unlink(missing_ok=True)
        elif command == "sh /data/otbr/start.sh":
            self.running = True
            self.events.append("restart-host")
        elif command.startswith("STATE=/tmp/rcp-native/state/paused-pids"):
            self.events.append("resume-openmiio")
        elif "OPENMIIO_READY_FOR_BLE_CACHE=" in command:
            assert "resume-openmiio" in self.events
            self.events.append("openmiio-ready")
        elif command not in ("sh /data/rcp-openmiio/start.sh", "sh /data/rcp-openmiio/start.sh --now",
                             "sh /data/mi-gw2-post-init/post-initctl.sh check"):
            raise AssertionError(command)
        return self.module.CommandResult(0, result)

    @property
    def marker(self):
        return self.tree / "interrupt-marker"

    def deploy(self, selection):
        self.engine.deploy(selection, self.module.DeployOptions(reboot=False))


def seed(module, assets, tree):
    for folder in ("data", "bin"):
        (tree / folder).mkdir(parents=True)
    for name, script in (("fw_manager.sh", STOCK_FW), ("app_monitor.sh", STOCK_MONITOR)):
        (tree / "bin" / name).write_text(script)
    for name in ("mbasis_cli", "agetprop"):
        stub = tree / "bin" / name
        stub.write_text("#!/usr/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    agent = tree / "data/openmiio_agent"
    agent.write_text("#!/usr/bin/sh\necho 'openmiio_agent version 1.2.1'\n")
    state = Offline(module, assets, tree)
    state.deploy(set(LABELS.values()))
    dest = tree / "data/otbr"
    (dest / "config.yaml").write_text("# fixture gateway-owned configuration\n")
    (dest / "secrets.yaml").write_text("# fixture gateway-owned secrets\n")
    (dest / "state").mkdir()
    (dest / "state/dataset").write_bytes(b"fixture dataset")
    for name in ("fw_manager.sh", "app_monitor.sh"):
        shutil.copy2(tree / "data/rcp-mode" / name, tree / "bin" / name)


def run():
    old_engine, old_resources = engine_modules(BASELINE / "auto-deploy/gui-python")
    new_engine, new_resources = engine_modules(PROJECT / "7-auto-deploy/gui-python")
    with tempfile.TemporaryDirectory(prefix="gw2-offline-upgrade-") as temp:
        work = Path(temp)
        old_assets = work / "old-assets"
        old_assets.mkdir()
        for name, path in old_resources.ASSET_MAP.items():
            shutil.copy2(BASELINE / path, old_assets / name)
        (old_assets / "SHA256SUMS").write_text("".join(
            f"{old_resources.sha256_file(path)}  {path.name}\n" for path in sorted(old_assets.iterdir())
        ))
        new_assets = new_resources.stage_assets(work / "new-assets")
        baseline = work / "baseline"
        seed(old_engine, old_assets, baseline)

        old_plan = old_engine.AutoDeployEngine(new_assets, "offline", 23, "", print, lambda *_: False)
        missing = set(old_plan._plan({"otbr"})) - set(old_plan.manifest)
        assert len(missing) == 5 and all("0.3.0" in name for name in missing)
        print("LEGACY_GUI_REQUIRES_OLD_ASSET_NAMES", len(missing))

        old_tree = work / "old-reinstall"
        shutil.copytree(baseline, old_tree)
        runner = Offline(old_engine, old_assets, old_tree)
        try:
            runner.deploy({"otbr"})
            raise AssertionError("legacy install should have rejected its existing isolation directory")
        except old_engine.GatewayError as exc:
            assert "Unmanaged /data/rcp-mode" in str(exc), exc
        print("LEGACY_RCP_REINSTALL_FAILURE_REPRODUCED")

        pristine = baseline / "data/otbr"
        for number, selection in enumerate(selection for count in range(1, 5)
                                           for selection in combinations(LABELS.values(), count)):
            tree = work / f"case-{number}"
            shutil.copytree(baseline, tree)
            runner = Offline(new_engine, new_assets, tree)
            runner.running = True
            runner.deploy(set(selection))
            otbr_selected = "otbr" in selection
            assert runner.flash_count == int(otbr_selected)
            if otbr_selected:
                assert runner.events.index("stop-host") < runner.events.index("probe")
            dest = tree / "data/otbr"
            assert (dest / "VERSION").read_text().strip() == ("0.3.2" if otbr_selected else "0.3.0")
            for name in ("config.yaml", "secrets.yaml", "state/dataset"):
                assert (dest / name).read_bytes() == (pristine / name).read_bytes()
            for label in ("openssh", "tun", "ble-cache"):
                assert (tree / "data" / label / "observed-version").read_text() == "0.3.0"
            assert (tree / "data/post_init.sh").read_bytes() == (baseline / "data/post_init.sh").read_bytes()
            assert runner.running and not runner.marker.exists()
            print("MIXED_UPGRADE_PASS", "+".join(selection))

        for label, firmware, permit, failure in (
            ("same-radio", "2.5.3/115200", True, False),
            ("cancelled", "3.1.1/230400", False, False),
            ("serial-failure", "3.1.1/230400", True, True),
            ("230400-to-115200", "3.1.1/230400", True, False),
        ):
            tree = work / label
            shutil.copytree(baseline, tree)
            runner = Offline(new_engine, new_assets, tree, firmware, permit)
            runner.running = True
            runner.fail_flash = failure
            failed = False
            try:
                runner.deploy({"otbr"})
            except new_engine.GatewayError:
                failed = True
            assert failed == (not permit or failure)
            assert runner.marker.exists() == failure
            assert runner.running != failure
            assert runner.flash_count == int(failure or label == "230400-to-115200")
            if permit and not failure:
                assert runner.firmware == "2.5.3/115200"
            print("UPGRADE_TRANSITION_PASS", label)


if __name__ == "__main__":
    run()
