"""Read-only SHA256 comparison of frozen release files against an installed gateway."""
import argparse
import os
import ipaddress
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway',default=os.environ.get('OTBR_TEST_HOST', 'GATEWAY_ADDRESS'))
    parser.add_argument('--ssh-port',type=int,default=2223)
    args=parser.parse_args()
    try: host=str(ipaddress.ip_address(args.gateway))
    except ValueError: parser.error('gateway must be an IP address')
    if not 1<=args.ssh_port<=65535: parser.error('invalid SSH port')
    root=Path(__file__).resolve().parent
    rows=json.loads((root/'release-audit/ARCHIVE-DEVICE-MATCH.json').read_text())
    rows+=json.loads((root/'release-audit/extra-public-dependencies.json').read_text())
    for link in json.loads((root/'release-audit/BOOT-CHAIN.json').read_text()):
        rows.append({'device_path':link['device_path'],'sha256':link['expected_component_hook_sha256']})
    expected={row['device_path']:row['sha256'] for row in rows}
    prefixes=('/data/openssh/','/data/tun/','/data/rcp-mode/','/data/rcp-openmiio/','/data/otbr/')
    for name,digest in expected.items():
        if not re.fullmatch(r'[A-Za-z0-9_./-]+',name) or '..' in Path(name).parts:
            raise SystemExit('Invalid audit path')
        if not name.startswith(prefixes) and name not in ('/data/openmiio_agent','/data/scripts/post_init.sh'): raise SystemExit('Path outside component whitelist')
        if name.endswith(('.yaml','.yml')) or 'ssh_host_' in name: raise SystemExit('Private/runtime path forbidden')
        if not re.fullmatch(r'[0-9a-f]{64}',digest): raise SystemExit('Invalid digest')
    command='for F in '+' '.join(shlex.quote(name) for name in sorted(expected))+'; do if [ -f "$F" ]; then sha256sum "$F"; else printf "MISSING  %s\\n" "$F"; fi; done'
    with tempfile.TemporaryDirectory(prefix='gw2-release-audit-') as directory:
        ssh=['ssh','-p',str(args.ssh_port),'-oBatchMode=yes','-oConnectTimeout=8',
             '-oStrictHostKeyChecking=accept-new','-oUserKnownHostsFile='+str(Path(directory)/'known_hosts'),'root@'+host]
        result=subprocess.run(ssh+[command],capture_output=True,text=True,timeout=30)
    if result.returncode: raise SystemExit('SSH audit failed; no device mutation performed.')
    actual={line.split()[1]:line.split()[0] for line in result.stdout.splitlines() if len(line.split())==2}
    failures=[]
    for name,digest in expected.items():
        if actual.get(name)!=digest: failures.append(name)
    if failures:
        for name in failures: print('DIFFERENT_OR_MISSING:',name)
        raise SystemExit('INSTALLED_FILE_AUDIT_FAILED: '+str(len(failures))+' mismatches')
    print('INSTALLED_FILE_AUDIT_PASS: '+str(len(expected))+' files exactly match the frozen release.')
    print('Only SHA256 of whitelisted public component files was read; no config/key read, restart, reset or flash.')
    print('RCP firmware is version-verified separately; no Flash byte comparison is claimed.')

if __name__=='__main__': main()
