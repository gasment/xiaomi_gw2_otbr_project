"""Package the optional BLE Spec patch; do not replace the main release."""
from pathlib import Path
import argparse
import hashlib
import io
import subprocess
import tarfile

here = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--version')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
version = args.version
if not version:
    version = next(p / 'VERSION' for p in here.parents if (p / 'VERSION').is_file()).read_text().strip()
if not version or any(c not in '0123456789.' for c in version):
    raise SystemExit('Unexpected project version')
out = args.output or here / 'deploy' / f'ble-spec-cache-{version}.tar.gz'
files = {'install.sh': (here / 'install.sh').read_bytes(), 'README.md': (here / 'README.md').read_bytes(),
         'LICENSE': (here / 'LICENSE').read_bytes(),
         'VERSION': (version + '\n').encode()}
files.update({'payload/' + p.name: p.read_bytes() for p in (here / 'payload').iterdir() if p.is_file()})
files['payload/spec-cache.lua'] = (here / 'src/spec-cache.lua').read_bytes()
files['payload/ble-cache-clock'] = (here / 'build/ble-cache-clock').read_bytes()
payload = {name.removeprefix('payload/'): data for name, data in files.items() if name.startswith('payload/')}
files['payload/files.sha256'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                                        for name, data in sorted(payload.items())).encode()
files['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                             for name, data in sorted(files.items())).encode()
for name, data in files.items():
    if name.endswith('.sh'):
        subprocess.run(['sh', '-n'], input=data, check=True)
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('wb') as raw:
    import gzip
    with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for name, data in sorted(files.items()):
                item = tarfile.TarInfo('ble-spec-cache/' + name)
                item.size = len(data)
                item.mode = 0o755 if name.endswith('.sh') or name.endswith('/ble-cache-clock') else 0o600
                item.mtime = 0
                tar.addfile(item, io.BytesIO(data))
out.with_name(out.name + '.sha256').write_text(hashlib.sha256(out.read_bytes()).hexdigest() + '  ' + out.name + '\n')
print('BLE_SPEC_CACHE_PACKAGE_PASS:', out.name, out.stat().st_size, 'bytes')
print('Optional patch only; main release and gateway were not changed.')
