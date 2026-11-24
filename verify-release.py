"""Verify the GitHub source edition without requiring external build resources."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dependencies',action='store_true')
parser.add_argument('--artifacts',type=Path,help='Optional external Release asset directory')
args=parser.parse_args()
count=0
for line in (root/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1)
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('SOURCE_MISMATCH: '+name)
    count+=1
skip={'.venv-build','0-build-src','.git','vendor','external','toolchains','deps','build','build-output','downloads','kernel-work','__pycache__'}
for directory,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[n for n in dirs if n not in skip and not (Path(directory)/n).is_symlink()]
    for name in files:
        p=Path(directory)/name
        if p.suffix=='.py':ast.parse(p.read_bytes(),filename=str(p))
        if p.suffix=='.sh':subprocess.run(['bash' if p.read_bytes().splitlines()[0] in (b'#!/bin/bash', b'#!/usr/bin/env bash') else 'sh','-n',str(p)],check=True,capture_output=True)
        if name in ('config.yaml','secrets.yaml') or re.fullmatch('ssh_host_.*_key',name):
            raise SystemExit('Runtime/private file in source edition')
for slot,target in json.loads((root/'dependencies/links.json').read_text()).items():
    p=root/slot
    if Path(target).is_absolute() or not (p.parent/target).resolve().is_relative_to(root/'0-build-src'):
        raise SystemExit('Unsafe deferred dependency link: '+slot)
    if p.is_symlink() and p.readlink().as_posix()!=target:
        raise SystemExit('Dependency link differs: '+slot)
if args.dependencies:
    subprocess.run(['python3',str(root/'tools/restore-dependencies.py'),'--check'],check=True)
if args.artifacts:
    external = args.artifacts.resolve()
    expected_assets = json.loads((root / 'dependencies/release-assets.json').read_text())
    locations = {
        "post-init-modular-0.3.0.tar.gz": "6-post-init/deploy/post-init-modular-0.3.0.tar.gz",
        "mi_gateway_2_openssh_deploy-0.3.0.tar.gz": "1-openssh/deploy/mi_gateway_2_openssh_deploy-0.3.0.tar.gz",
        "mi_gateway_2_tun_deploy-0.3.0.tar.gz": "2-tun-driver/deploy/mi_gateway_2_tun_deploy-0.3.0.tar.gz",
        "rcp-native-0.3.2.tar.gz": "3-rcp-mode/deploy/rcp-native-0.3.2.tar.gz",
        "rcp-mode-0.3.2.tar.gz": "3-rcp-mode/deploy/rcp-mode-0.3.2.tar.gz",
        "rcp-openmiio-0.3.2.tar.gz": "4-rcp-openmiio/deploy/rcp-openmiio-0.3.2.tar.gz",
        "mi-gw2-otbr-0.3.2.tar.gz": "5-otbr/deploy/mi-gw2-otbr-0.3.2.tar.gz",
        "rcp-recovery-update-0.3.0.tar.gz": "5-otbr/deploy/rcp-recovery-update-0.3.0.tar.gz",
        "ble-spec-cache-0.3.0.tar.gz": "8-xiaomi-gateway3-patch/ble-spec-cache/deploy/ble-spec-cache-0.3.0.tar.gz",
        "MiGateway2AutoDeploy-0.3.1.exe": "7-auto-deploy/gui-python/deploy/MiGateway2AutoDeploy-0.3.1.exe",
        "spinel-probe-0.3.2": "3-rcp-mode/deploy/tools/spinel-probe",
        "openmiio_agent-1.2.1-arm": "4-rcp-openmiio/deploy/dependencies/openmiio_agent"
    }
    for name, expected in expected_assets.items():
        path = external / name
        if not path.is_file():
            path = external / locations[name]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('RELEASE_ASSET_MISMATCH: ' + name)
        if name.endswith('.tar.gz'):
            with tarfile.open(path) as tar:
                contents = {member.name: tar.extractfile(member).read() for member in tar if member.isfile()}
            top = next(iter(contents)).split('/')[0]
            version = contents[top + '/VERSION'].decode().strip()
            if not name.endswith('-' + version + '.tar.gz'):
                raise SystemExit('Release version differs: ' + name)
            for line in contents[top + '/SHA256SUMS'].decode().splitlines():
                digest, relative = line.split('  ', 1)
                if hashlib.sha256(contents[top + '/' + relative]).hexdigest() != digest:
                    raise SystemExit('Release inner hash mismatch: ' + name + '/' + relative)
    print('EXTERNAL_RELEASE_ASSETS_PASS:', len(expected_assets))
print('GITHUB_SOURCE_VERIFY_PASS version='+(root/'VERSION').read_text().strip()+' files='+str(count))
print('Default check covers source only; missing local SDK/toolchains and Release assets are not claimed present. No compiler or device operation.')
