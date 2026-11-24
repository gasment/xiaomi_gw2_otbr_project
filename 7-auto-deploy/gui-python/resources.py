from __future__ import annotations

import atexit
import hashlib
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = (HERE / "VERSION").read_text(encoding="utf-8").strip()
VERSION_PATTERN = r"(?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)"

COMPONENT_DIRS = {
    "openssh": "1-openssh",
    "tun": "2-tun-driver",
    "ble-cache": "8-xiaomi-gateway3-patch/ble-spec-cache",
    "otbr": "5-otbr",
}
COMPONENT_ASSETS = {
    "openssh": "mi_gateway_2_openssh_deploy",
    "tun": "mi_gateway_2_tun_deploy",
    "ble-cache": "ble-spec-cache",
    "otbr": "mi-gw2-otbr",
}
OTBR_ASSETS = {
    "rcp-native": "3-rcp-mode",
    "rcp-mode": "3-rcp-mode",
    "rcp-openmiio": "4-rcp-openmiio",
}
SUPPORT_ASSETS = {
    "rcp-recovery-update-0.3.0.tar.gz": "5-otbr/deploy/rcp-recovery-update-0.3.0.tar.gz",
    "post-init-modular-0.3.0.tar.gz": "6-post-init/deploy/post-init-modular-0.3.0.tar.gz",
    "openmiio_agent-1.2.1-arm": "4-rcp-openmiio/deploy/dependencies/openmiio_agent",
}


def version_tuple(value: str) -> tuple[int, ...]:
    if re.fullmatch(VERSION_PATTERN, value):
        return tuple(int(part) for part in value.split("."))
    return ()


def asset_catalog(manifest: dict[str, str]) -> dict[str, str]:
    names = {}
    for stem in (*COMPONENT_ASSETS.values(), *OTBR_ASSETS, "spinel-probe"):
        extension = "" if stem == "spinel-probe" else r"[.]tar[.]gz"
        pattern = re.compile(re.escape(stem) + "-" + VERSION_PATTERN + extension)
        matches = [name for name in manifest if pattern.fullmatch(name)]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one bundle asset for {stem}")
        names[stem] = matches[0]
    otbr_stem = COMPONENT_ASSETS["otbr"]
    otbr = asset_version(otbr_stem, names[otbr_stem])
    if any(asset_version(stem, names[stem]) != otbr for stem in (*OTBR_ASSETS, "spinel-probe")):
        raise ValueError("OTBR, RCP and the Spinel probe must come from the same bundle")
    return names


def asset_version(stem: str, filename: str) -> str:
    return filename.removeprefix(stem + "-").removesuffix(".tar.gz")


def check_assets(assets: Path) -> None:
    manifest = load_manifest(assets)
    catalog = asset_catalog(manifest)
    for name in (*catalog.values(), *SUPPORT_ASSETS):
        verify_asset(assets, manifest, name)
    for stem, name in catalog.items():
        if not name.endswith(".tar.gz"):
            continue
        with tarfile.open(assets / name) as archive:
            versions = [
                member for member in archive
                if member.isfile() and member.name.count("/") == 1 and member.name.endswith("/VERSION")
            ]
            if len(versions) != 1 or versions[0].size > 32:
                raise ValueError(f"Missing component VERSION: {name}")
            payload_version = archive.extractfile(versions[0]).read().decode("ascii").strip()
            if payload_version != asset_version(stem, name):
                raise ValueError(f"Component VERSION differs from filename: {name}")


def stage_assets(target: Path) -> Path:
    project = HERE.parents[1]
    sources = dict(SUPPORT_ASSETS)
    versions = {}
    for component, directory in COMPONENT_DIRS.items():
        version = (project / directory / "VERSION").read_text().strip()
        if not version_tuple(version):
            raise ValueError(f"Invalid VERSION for {component}")
        versions[component] = version
        name = f"{COMPONENT_ASSETS[component]}-{version}.tar.gz"
        sources[name] = f"{directory}/deploy/{name}"
    otbr = versions["otbr"]
    for stem, directory in OTBR_ASSETS.items():
        name = f"{stem}-{otbr}.tar.gz"
        sources[name] = f"{directory}/deploy/{name}"
    sources[f"spinel-probe-{otbr}"] = "3-rcp-mode/deploy/tools/spinel-probe"

    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, source in sources.items():
        destination = target / name
        shutil.copy2(project / source, destination)
        rows.append(f"{sha256_file(destination)}  {name}")
    (target / "SHA256SUMS").write_text("\n".join(sorted(rows)) + "\n", encoding="utf-8")
    check_assets(target)
    return target


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

    target = Path(tempfile.mkdtemp(prefix="mi-gw2-python-assets-"))
    atexit.register(shutil.rmtree, target, ignore_errors=True)
    return stage_assets(target)


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

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("stage", "check"):
        raise SystemExit("Usage: resources.py (stage|check) ASSETS_DIRECTORY")
    path = Path(sys.argv[2])
    if sys.argv[1] == "stage":
        stage_assets(path)
    else:
        check_assets(path)
