"""Build a Windows deployment ZIP from component deploy assets; never compile or access a gateway."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=root.parent/'release')
parser.add_argument('--artifacts',type=Path,help='Optional legacy flat component asset directory; default: component deploy directories')
args=parser.parse_args()
output=args.output.resolve()
if output==root or output.is_relative_to(root):parser.error('Release output must stay outside the source project.')
subprocess.run(['python3',str(root/'verify-release.py')],check=True)
version=(root/'VERSION').read_text().strip()
specs=json.loads((root/('release-audit/ALL-COMPONENTS-'+version+'.json')).read_text())['archives']
if len(specs)!=7:raise SystemExit('Expected seven component archives')
def sha(data):return hashlib.sha256(data).hexdigest()
def source(relative,name):return args.artifacts.resolve()/name if args.artifacts else root/relative
assets={}
contents={}
for row in specs:
    name=Path(row['artifact']).name
    if not name.endswith('-'+version+'.tar.gz'):raise SystemExit('Component version mismatch: '+name)
    path=source(row['artifact'],name)
    data=path.read_bytes()
    if sha(data)!=row['sha256']:raise SystemExit('Component digest mismatch: '+name)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        files={}
        for m in tf.getmembers():
            p=Path(m.name)
            if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir()):raise SystemExit('Unsafe component member')
            if m.isfile():
                if m.name in files:raise SystemExit('Duplicate component member')
                files[m.name]=tf.extractfile(m).read()
    tops={n.split('/')[0] for n in files}
    if len(tops)!=1:raise SystemExit('Component root mismatch')
    top=tops.pop()
    if files[top+'/VERSION'].decode().strip()!=version:raise SystemExit('Inner version mismatch')
    checked=set()
    for line in files[top+'/SHA256SUMS'].decode().splitlines():
        h,n=line.split('  ',1)
        if n in checked or sha(files[top+'/'+n])!=h:raise SystemExit('Inner component digest mismatch')
        checked.add(n)
    if checked!={n[len(top)+1:] for n in files if n!=top+'/SHA256SUMS'}:raise SystemExit('Incomplete component manifest')
    assets[name]=path;contents[row['artifact']]=files
for row in json.loads((root/'release-audit/SOURCE-PAYLOAD-MAP.json').read_text()):
    if (root/row['source']).read_bytes()!=contents[row['artifact']][row['member']]:raise SystemExit('Source/payload mismatch: '+row['source'])
assets['spinel-probe-'+version]=source('3-rcp-mode/deploy/tools/spinel-probe','spinel-probe-'+version)
assets['openmiio_agent-1.2.1-arm']=source('4-rcp-openmiio/deploy/dependencies/openmiio_agent','openmiio_agent-1.2.1-arm')
pinned=root/'dependencies/release-assets.json'
if pinned.is_file():
    expected_assets=json.loads(pinned.read_text())
    if set(expected_assets)!=set(assets):raise SystemExit('Release asset set mismatch')
    for name,path in assets.items():
        if sha(path.read_bytes())!=expected_assets[name]:raise SystemExit('Release asset mismatch: '+name)
rows=json.loads((root/'release-audit/ARCHIVE-DEVICE-MATCH.json').read_text())
rows+=json.loads((root/'release-audit/extra-public-dependencies.json').read_text())
expected={r['device_path']:r['sha256'] for r in rows}
for row in json.loads((root/'release-audit/BOOT-CHAIN.json').read_text()):expected[row['device_path']]=row['expected_component_hook_sha256']
if len(expected)!=45:raise SystemExit('Unexpected installed-file verification set')
for name in expected:
    if not name.startswith('/data/') or '..' in Path(name).parts or name.endswith(('.yaml','.yml')) or 'ssh_host_' in name:raise SystemExit('Unsafe installed-file expectation')
output.mkdir(parents=True,exist_ok=True)
notes_path=output/'RELEASE-NOTES.md'
notes=notes_path.read_bytes() if notes_path.exists() else (root/'auto-deploy/README.md').read_bytes()
with tempfile.TemporaryDirectory(prefix='gw2-release-') as directory:
    temp=Path(directory)
    stage=temp/'mi-gw2-auto-deploy';(stage/'assets').mkdir(parents=True)
    for name,path in assets.items():shutil.copy2(path,stage/'assets'/name)
    shutil.copy2(root/'auto-deploy/install.sh',stage/'install.sh')
    (stage/'VERSION').write_text(version+'\n')
    (stage/'README.md').write_bytes((root/'auto-deploy/README.md').read_bytes())
    (stage/'installed-files.sha256').write_text(''.join(expected[n]+'  '+n+'\n' for n in sorted(expected)))
    files=sorted(p for p in stage.rglob('*') if p.is_file())
    (stage/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(stage).as_posix()+'\n' for p in files))
    subprocess.run(['sh','-n',str(stage/'install.sh')],check=True)
    subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=stage,check=True,stdout=subprocess.DEVNULL)
    name='mi-gw2-auto-deploy-'+version+'.tar.gz'
    bundle=temp/name
    with tarfile.open(bundle,'w:gz') as tf:tf.add(stage,arcname=stage.name)
    (temp/(name+'.sha256')).write_text(sha(bundle.read_bytes())+'  '+name+'\n')
    (temp/'RELEASE-NOTES.md').write_bytes(notes)
    windows=['Deploy-Gateway.ps1','GatewayDeployNet.cs','Deploy-Gateway.cmd']
    for n in windows:shutil.copy2(root/'auto-deploy'/n,temp/n)
    zipname='mi-gw2-windows-deploy-'+version+'.zip'
    pending=output/('.'+zipname+'.new')
    members=[name,name+'.sha256','RELEASE-NOTES.md']+windows
    try:
        with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for n in members:z.write(temp/n,arcname=n)
        with zipfile.ZipFile(pending) as z:
            if z.testzip() is not None or z.read('RELEASE-NOTES.md')!=notes:raise SystemExit('ZIP verification failed')
        if notes_path.exists() and notes_path.read_bytes()!=notes:raise SystemExit('Release notes changed during packaging; retry')
        os.replace(pending,output/zipname)
    finally:
        if pending.exists():pending.unlink()
    checksum=output/(zipname+'.sha256')
    checksum.write_text(sha((output/zipname).read_bytes())+'  '+zipname+'\n')
    if not notes_path.exists():notes_path.write_bytes(notes)
print('WINDOWS_RELEASE_READY:',output/zipname)
print('Component assets read from deploy directories; full gateway bundle stays inside ZIP. Existing RELEASE-NOTES.md preserved.')
