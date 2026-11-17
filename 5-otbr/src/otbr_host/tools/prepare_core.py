"""Fetch/verify locked OTBR source. Never build or operate a radio."""
import argparse
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent.parent
lock = json.loads((root / 'deps.lock.json').read_text())['ot-br-posix']
dest = root / 'vendor/ot-br-posix'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify', action='store_true')
args = parser.parse_args()

def run(argv, **kwargs):
    p = subprocess.run(argv, capture_output=True, text=True, **kwargs)
    if p.returncode:
        raise SystemExit(p.stderr[-3000:] or p.stdout[-3000:])
    return p.stdout.strip()

if not dest.exists():
    if args.verify:
        raise SystemExit('Missing OTBR source. Run sh prepare-core.sh first.')
    dest.parent.mkdir(exist_ok=True)
    run(['git', 'init', str(dest)])
    run(['git', '-C', str(dest), 'remote', 'add', 'origin', lock['url']])
    print('Fetching locked OTBR commit...', flush=True)
    run(['git', '-C', str(dest), 'fetch', '--depth', '1', 'origin', lock['commit']])
    run(['git', '-C', str(dest), 'checkout', '--detach', 'FETCH_HEAD'])
if run(['git', '-C', str(dest), 'rev-parse', 'HEAD']) != lock['commit']:
    raise SystemExit('Existing OTBR revision differs; refusing automatic replacement.')
if run(['git', '-C', str(dest), 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=all']):
    raise SystemExit('OTBR tracked files have edits; inspect before building.')
if not args.verify:
    print('Preparing pinned OpenThread and TLS submodules...', flush=True)
    run(['git', '-C', str(dest), 'submodule', 'update', '--init', '--recursive', '--depth', '1', '--', 'third_party/openthread/repo'])
    # A submodule update is not allowed to silently discard local edits.
status = run(['git', '-C', str(dest), 'submodule', 'status', '--recursive'])
expected = {}
for line in lock['submodules']:
    # cJSON/httplib are recorded but intentionally uninitialized for baseline.
    fields = line.strip().lstrip('-+').split()
    if fields and fields[1].startswith('third_party/openthread/'):
        expected[fields[1]] = fields[0]
for relative, revision in expected.items():
    path = dest / relative
    if not (path / '.git').exists():
        raise SystemExit('Missing pinned nested dependency: ' + relative)
    if run(['git', '-C', str(path), 'rev-parse', 'HEAD']) != revision:
        raise SystemExit('Nested dependency revision mismatch: ' + relative)
    if run(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=all']):
        raise SystemExit('Nested dependency has local source edits: ' + relative)
spinel = (dest / 'third_party/openthread/repo/src/lib/spinel/spinel.h').read_text()
def version(name):
    match = re.search(r'^#define\s+' + name + r'\s+(\d+)\s*$', spinel, re.M)
    if not match: raise SystemExit('Missing Spinel version constant: ' + name)
    return int(match.group(1))
api = version('SPINEL_RCP_API_VERSION')
minimum = version('SPINEL_MIN_HOST_SUPPORTED_RCP_API_VERSION')
if api < 4 or minimum > 10:
    raise SystemExit('Host/RCP API version thresholds do not match the probed radio.')
print(f'CORE_SOURCE_LOCK_PASS: host API={api}, minimum RCP API={minimum}; radio API=10, minimum host API=4.')
print('Version thresholds match; this is not a full runtime compatibility test.')
