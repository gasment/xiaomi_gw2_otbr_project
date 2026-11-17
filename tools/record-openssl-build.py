"""Validate and explicitly pin a locally rebuilt ARM OpenSSL; never compile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
mode=parser.add_mutually_exclusive_group(required=True)
mode.add_argument('--capture',action='store_true',help='Validate installed archives and record local build provenance only')
mode.add_argument('--accept',action='store_true',help='Validate recorded build and update only OpenSSL dependency pins')
args=parser.parse_args()
base=root/'0-build-src/openssl/arm'
source=root/'0-build-src/openssl/source'
prefix=root/'0-build-src/toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-'
commit='84dda7853c130429210b37bee9e5b62366ca8bce'
actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if actual!=commit:raise SystemExit('OpenSSL source commit differs')
files=['lib/libssl.a','lib/libcrypto.a','include/openssl/opensslv.h']
hashes={}
for name in files:
    p=base/name
    if not p.is_file():raise SystemExit('Missing rebuilt dependency: '+name)
    hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    if name.endswith('.a'):
        with p.open('rb') as stream:
            if stream.read(8)!=b'!<arch>\n':raise SystemExit('Not a static archive: '+name)
        header=subprocess.check_output([str(prefix)+'readelf','-h',str(p)],text=True,env=dict(os.environ,LC_ALL='C'))
        machines=re.findall(r'^\s*Machine:\s*(.+)$',header,re.M)
        classes=re.findall(r'^\s*Class:\s*(.+)$',header,re.M)
        if not machines or any(v.strip()!='ARM' for v in machines) or not classes or any(v.strip()!='ELF32' for v in classes):
            raise SystemExit('Non-ARM32 object in '+name)
if list((base/'lib').glob('*.so*')):raise SystemExit('Unexpected shared OpenSSL library')
record=base/'BUILD-INFO.json'
if args.capture:
    info={'source_commit':commit,'target':'linux-armv4','abi':'ARMv7 musl hard-float','configure_profile':'no-shared no-tests no-module no-dso; Cortex-A7 NEON-VFPv4; see tools/build-openssl.sh','files':hashes}
    record.write_text(json.dumps(info,indent=2)+'\n')
    print('OPENSSL_ARM_STATIC_VALIDATED; only local BUILD-INFO.json written; dependency pins unchanged')
else:
    if not record.is_file():raise SystemExit('No build provenance; run the documented OpenSSL build first')
    info=json.loads(record.read_text())
    if info.get('source_commit')!=commit or info.get('target')!='linux-armv4' or info.get('files')!=hashes:
        raise SystemExit('Installed library differs from the recorded local build')
    lock_path=root/'dependencies/lock.json'
    lock=json.loads(lock_path.read_text())
    row=next(x for x in lock if x['name']=='openssl-arm')
    row['marker_sha256']=hashes
    row['baseline']='locally rebuilt; does not alter the frozen Release acceptance records'
    host_path=root/'5-otbr/src/otbr_host/deps.lock.json'
    host=json.loads(host_path.read_text());host['openssl-arm']['files']=hashes
    updates={lock_path:json.dumps(lock,indent=2)+'\n',host_path:json.dumps(host,indent=2)+'\n'}
    for path,text in updates.items():
        temporary=path.with_name(path.name+'.new');temporary.write_text(text);temporary.replace(path)
    # Keep the source-edition checksum manifest consistent with these explicit changes.
    manifest=root/'SHA256SUMS';lines=manifest.read_text().splitlines();names={str(p.relative_to(root)) for p in updates}
    for i,line in enumerate(lines):
        _,name=line.split('  ',1)
        if name in names:lines[i]=hashlib.sha256((root/name).read_bytes()).hexdigest()+'  '+name
    manifest.write_text('\n'.join(lines)+'\n')
    print('OPENSSL_LOCAL_BASELINE_RECORDED: dependency pins updated; frozen binaries and their acceptance hashes unchanged')
