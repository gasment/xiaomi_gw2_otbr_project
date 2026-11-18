"""Read-only disk checks; never print passwords, tokens or whole config entries."""
import argparse
import ast
import ipaddress
import json
from pathlib import Path


def inspect_config(directory):
    errors = 0
    root = Path(directory)
    print("DISK_CHECK_ONLY: this does not inspect hooks in the running HA process")
    try:
        tree = ast.parse((root / "custom_components/__init__.py").read_bytes())
        aliases = {a.asname or a.name for node in tree.body if isinstance(node, ast.ImportFrom)
                   and node.module == "xiaomi_gateway3_telnet_patch.early"
                   for a in node.names if a.name == "install_early_hooks"}
        active = any(isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                     and isinstance(node.value.func, ast.Name) and node.value.func.id in aliases
                     for node in tree.body)
    except (OSError, SyntaxError):
        active = False
    print("BOOTSTRAP_ON_DISK=" + ("present" if active else "missing_or_invalid"))
    errors += not active
    try:
        version = json.loads((root / "custom_components/xiaomi_gateway3/manifest.json").read_text())["version"]
        compatible = version == "4.3.0"
    except (OSError, ValueError, KeyError, TypeError):
        compatible = False
    print("UPSTREAM_REVIEWED_VERSION=" + ("yes" if compatible else "no"))
    errors += not compatible
    try:
        entries = json.loads((root / ".storage/core.config_entries").read_text())["data"]["entries"]
        if not isinstance(entries, list):
            raise ValueError
        protected = set()
        for entry in entries:
            if entry.get("domain") != "xiaomi_gateway3_telnet_patch":
                continue
            data = entry.get("data", {})
            try:
                host = str(ipaddress.ip_address(data.get("host", "")))
            except ValueError:
                print("PATCH_ENTRY=invalid_address")
                errors += 1
                continue
            password = data.get("password")
            valid = isinstance(password, str) and bool(password)
            print("PATCH_ENTRY host=" + host + " password=" + ("configured" if valid else "missing"))
            if valid:
                protected.add(host)
            else:
                errors += 1
        for entry in entries:
            if entry.get("domain") != "xiaomi_gateway3":
                continue
            host = entry.get("options", {}).get("host")
            if not host:
                continue  # Cloud-account entries have no gateway host.
            try:
                host = str(ipaddress.ip_address(host))
            except ValueError:
                print("GATEWAY_LOGIN_CONFIG=non_ip_host_requires_review")
                errors += 1
                continue
            covered = host in protected
            print("GATEWAY host=" + host + " password_login_config=" + ("matched" if covered else "missing"))
            errors += not covered
    except (OSError, ValueError, KeyError, TypeError):
        print("CONFIG_ENTRIES=unreadable_or_invalid")
        errors += 1
    print("Running-process confirmation: look for GW2_PASSWORD_PATCH_EARLY_GUARD_ACTIVE and GW2_PASSWORD_PATCH_COMMAND_GUARD_ACTIVE in HA startup logs.")
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-directory", default=str(Path(__file__).resolve().parents[2]))
    raise SystemExit(inspect_config(parser.parse_args().config_directory))
