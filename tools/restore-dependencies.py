"""Restore relative build links after resources are supplied; never download or compile."""
import argparse
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--component',choices=['all','1','2','3','4','5'],default='all')
parser.add_argument('--create-links',action='store_true')
parser.add_argument('--check',action='store_true')
args=parser.parse_args()
lock=json.loads((root/'dependencies/lock.json').read_text())
links=json.loads((root/'dependencies/links.json').read_text())
# Restore an optional generated build adapter before checking its marker.
if args.create_links:
    noise=root/'0-build-src/vendor/noise-c'
    if noise.is_dir() and not (noise/'CMakeLists.txt').exists():
        (noise/'CMakeLists.txt').write_bytes((root/'dependencies/overlays/noise-c/CMakeLists.txt').read_bytes())
if args.create_links:
    kernel=root/'0-build-src/linux/linux-chenxing-vendor-slop-ikayaki_dlm00v014'
    if kernel.is_dir() and not (kernel/'.config').exists():
        (kernel/'.config').write_bytes((root/'dependencies/kernel-source.config').read_bytes())
missing=[]
for row in lock:
    wanted=row['components'] and (args.component=='all' or args.component in row['components'])
    if not wanted: continue
    base=root/row['path']
    if not base.is_dir():
        missing.append(row['path']); continue
    # Header/library and source anchors identify the actual pinned baseline.
    for name,digest in row.get('marker_sha256',{}).items():
        p=base/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            missing.append(row['path']+'/'+name+' (missing or hash differs)')
if args.create_links:
    noise=root/'0-build-src/vendor/noise-c'
    if noise.is_dir():
        original=root/'dependencies/overlays/noise-c/CMakeLists.txt'
        if not (noise/'CMakeLists.txt').exists():
            (noise/'CMakeLists.txt').write_bytes(original.read_bytes())
    yaml=root/'0-build-src/vendor/yaml-cpp'
    if yaml.is_dir() and not (yaml/'.source-hashes.json').exists():
        hashes={str(p.relative_to(yaml)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in yaml.rglob('*') if p.is_file() and '.git' not in p.relative_to(yaml).parts and not p.is_symlink()}
        (yaml/'.source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    for slot,target in links.items():
        if args.component!='all' and not slot.startswith(args.component+'-'):continue
        p=root/slot
        resolved=(p.parent/target).resolve()
        if not resolved.is_relative_to(root/'0-build-src'):
            raise SystemExit('Unsafe dependency link: '+slot)
        if not resolved.exists():continue
        if p.is_symlink():
            if p.readlink().as_posix()!=target:raise SystemExit('Different link already exists: '+slot)
            continue
        if p.exists():raise SystemExit('Existing regular path would be overwritten: '+slot)
        p.parent.mkdir(parents=True,exist_ok=True)
        p.symlink_to(target,target_is_directory=True)
        print('LINK_CREATED:',slot)
if missing:
    for item in missing:print('RESOURCE_REQUIRED:',item)
    raise SystemExit('Build resources incomplete; see BUILD-RESOURCES.md. No compiler was run.')
print('BUILD_RESOURCES_READY component='+args.component+'; no download or compilation')
