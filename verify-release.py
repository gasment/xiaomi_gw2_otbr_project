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
    external=args.artifacts.resolve()
    artifact_rows=json.loads((root/('release-audit/ALL-COMPONENTS-'+(root/'VERSION').read_text().strip()+'.json')).read_text())['archives']
    locations={Path(row['artifact']).name:row['artifact'] for row in artifact_rows}
    locations['spinel-probe-'+(root/'VERSION').read_text().strip()]='3-rcp-mode/deploy/tools/spinel-probe'
    locations['openmiio_agent-1.2.1-arm']='4-rcp-openmiio/deploy/dependencies/openmiio_agent'
    def artifact_path(name):
        flat=external/name
        return flat if flat.is_file() else external/locations[name]
    for name,expected in json.loads((root/'dependencies/release-assets.json').read_text()).items():
        p=artifact_path(name)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise SystemExit('RELEASE_ASSET_MISMATCH: '+name)
    # Published artifact hashes stay verifiable without vendoring the archives.
    rows=json.loads((root/('release-audit/ALL-COMPONENTS-'+(root/'VERSION').read_text().strip()+'.json')).read_text())['archives']
    contents={}
    for row in rows:
        p=artifact_path(Path(row['artifact']).name)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise SystemExit('RELEASE_ASSET_MISMATCH: '+p.name)
        with tarfile.open(p) as tf:
            data={m.name:tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
        top=next(iter(data)).split('/')[0]
        if data[top+'/VERSION'].decode().strip()!=(root/'VERSION').read_text().strip():
            raise SystemExit('Release version differs: '+p.name)
        for line in data[top+'/SHA256SUMS'].decode().splitlines():
            expected,name=line.split('  ',1)
            if hashlib.sha256(data[top+'/'+name]).hexdigest()!=expected:raise SystemExit('Release inner hash mismatch')
        contents[row['artifact']]=data
    for row in json.loads((root/'release-audit/SOURCE-PAYLOAD-MAP.json').read_text()):
        if (root/row['source']).read_bytes()!=contents[row['artifact']][row['member']]:
            raise SystemExit('Source/runtime payload differs: '+row['source'])
    print('EXTERNAL_RELEASE_ASSETS_PASS: 7 archives; source payloads match')
print('GITHUB_SOURCE_VERIFY_PASS version='+(root/'VERSION').read_text().strip()+' files='+str(count))
print('Default check covers source only; missing local SDK/toolchains and Release assets are not claimed present. No compiler or device operation.')
