"""Fetch pinned parser source only; never invoke a compiler or modify the gateway."""
from pathlib import Path
import hashlib
import json
import tarfile
import tempfile
import urllib.request

root = Path(__file__).resolve().parent.parent
lock = json.loads((root / 'deps.lock.json').read_text())['yaml-cpp']
dest = root / 'vendor/yaml-cpp'
if dest.exists():
    files = json.loads((dest / '.source-hashes.json').read_text())
    for name, expected in files.items():
        if hashlib.sha256((dest / name).read_bytes()).hexdigest() != expected:
            raise SystemExit('Existing yaml-cpp source differs; refusing to overwrite local changes.')
    print('Pinned yaml-cpp source already present; checksums verified. No build performed.')
    raise SystemExit(0)
downloads = root / 'downloads'
downloads.mkdir(exist_ok=True)
archive = downloads / 'yaml-cpp-0.9.0.tar.gz'
if not archive.exists():
    with urllib.request.urlopen(lock['url'], timeout=60) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise SystemExit('Dependency archive exceeds limit.')
    if hashlib.sha256(data).hexdigest() != lock['sha256']:
        raise SystemExit('Downloaded dependency hash mismatch.')
    archive.write_bytes(data)
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
    raise SystemExit('Cached dependency hash mismatch.')
dest.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=dest.parent) as temporary:
    stage = Path(temporary)
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            p = Path(member.name)
            if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):
                raise SystemExit('Unsupported dependency archive member.')
        source.extractall(stage, filter='data')
    roots = list(stage.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise SystemExit('Unexpected dependency archive layout.')
    hashes = {p.relative_to(roots[0]).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in roots[0].rglob('*') if p.is_file()}
    (roots[0] / '.source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    roots[0].rename(dest)
print('Pinned yaml-cpp source ready. No build or gateway operation performed.')
