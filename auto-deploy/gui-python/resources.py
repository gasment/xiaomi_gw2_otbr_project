from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

VERSION = "0.3.0"
ASSET_MAP = {
    "post-init-modular-0.3.0.tar.gz": "tools/post-init/deploy/post-init-modular-0.3.0.tar.gz",
    "mi_gateway_2_openssh_deploy-0.3.0.tar.gz": "1-openssh/deploy/mi_gateway_2_openssh_deploy-0.3.0.tar.gz",
    "mi_gateway_2_tun_deploy-0.3.0.tar.gz": "2-tun-driver/deploy/mi_gateway_2_tun_deploy-0.3.0.tar.gz",
    "ble-spec-cache-0.3.0.tar.gz": "xiaomi_gateway3_patch/ble-spec-cache/deploy/ble-spec-cache-0.3.0.tar.gz",
    "rcp-native-0.3.0.tar.gz": "3-rcp-mode/deploy/rcp-native-0.3.0.tar.gz",
    "rcp-mode-0.3.0.tar.gz": "3-rcp-mode/deploy/rcp-mode-0.3.0.tar.gz",
    "rcp-openmiio-0.3.0.tar.gz": "4-rcp-openmiio/deploy/rcp-openmiio-0.3.0.tar.gz",
    "mi-gw2-otbr-0.3.0.tar.gz": "5-otbr/deploy/mi-gw2-otbr-0.3.0.tar.gz",
    "rcp-recovery-update-0.3.0.tar.gz": "5-otbr/deploy/rcp-recovery-update-0.3.0.tar.gz",
    "spinel-probe-0.3.0": "3-rcp-mode/deploy/tools/spinel-probe",
    "openmiio_agent-1.2.1-arm": "4-rcp-openmiio/deploy/dependencies/openmiio_agent",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return app_dir()


def _asset_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        bundled_dir() / "assets",
        here / "assets",
    ]


def resolve_assets() -> Path:
    override = os.environ.get("MI_GW2_GUI_ASSETS")
    candidates = ([Path(override)] if override else []) + _asset_candidates()
    for candidate in candidates:
        if (candidate / "SHA256SUMS").is_file():
            return candidate

    here = Path(__file__).resolve().parent
    project_root = here.parents[1]
    sources = {name: project_root / rel for name, rel in ASSET_MAP.items()}
    if all(source.is_file() for source in sources.values()):
        target = Path(tempfile.gettempdir()) / f"mi-gw2-python-assets-{VERSION}"
        target.mkdir(parents=True, exist_ok=True)
        rows = []
        for name, source in sources.items():
            destination = target / name
            shutil.copy2(source, destination)
            rows.append(f"{sha256_file(destination)}  {name}")
        (target / "SHA256SUMS").write_text(
            "\n".join(sorted(rows)) + "\n",
            encoding="utf-8",
        )
        return target
    raise FileNotFoundError("GUI deployment assets are missing.")


def load_manifest(assets: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (assets / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if len(line) > 66:
            result[line[66:].strip()] = line[:64].lower()
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def verify_asset(assets: Path, manifest: dict[str, str], name: str) -> Path:
    path = assets / name
    expected = manifest.get(name)
    if not expected:
        raise ValueError(f"Checksum missing: {name}")
    if not path.is_file():
        raise FileNotFoundError(f"Asset missing: {name}")
    if sha256_file(path) != expected:
        raise ValueError(f"Local asset checksum mismatch: {name}")
    return path


def icon_path() -> Path | None:
    for path in (
        bundled_dir() / "icon.png",
        Path(__file__).resolve().parent / "icon.png",
    ):
        if path.is_file():
            return path
    return None
