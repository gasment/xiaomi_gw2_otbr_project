"""Fetch the independent Noise library only; never compile."""
from pathlib import Path
import hashlib
import json
import tarfile
import tempfile
import urllib.request

root=Path(__file__).resolve().parent.parent
lock=json.loads((root/'deps.lock.json').read_text())['noise-c']
archive=root/'downloads/noise-c-0.1.31.tar.gz'
archive.parent.mkdir(exist_ok=True)
if not archive.exists():
    data=urllib.request.urlopen(lock['url'],timeout=60).read(8*1024*1024+1)
    if len(data)>8*1024*1024 or hashlib.sha256(data).hexdigest()!=lock['sha256']:
        raise SystemExit('Noise source archive integrity check failed.')
    archive.write_bytes(data)
if hashlib.sha256(archive.read_bytes()).hexdigest()!=lock['sha256']:
    raise SystemExit('Cached Noise archive integrity check failed.')
dest=root/'vendor/noise-c'
dest.parent.mkdir(exist_ok=True)
with tarfile.open(archive) as source:
    members=source.getmembers()
    for member in members:
        path=Path(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsupported source archive member.')
    if not dest.exists():
        with tempfile.TemporaryDirectory(dir=dest.parent) as td:
            source.extractall(td,filter='data')
            roots=list(Path(td).iterdir())
            if len(roots)!=1 or not roots[0].is_dir():raise SystemExit('Invalid Noise source layout.')
            roots[0].rename(dest)
    for member in members:
        if not member.isfile():continue
        relative=Path(*Path(member.name).parts[1:])
        original=source.extractfile(member).read()
        if not (dest/relative).is_file() or hashlib.sha256((dest/relative).read_bytes()).digest()!=hashlib.sha256(original).digest():
            raise SystemExit('Noise source has local edits; refusing overwrite: '+str(relative))
print('NOISE_SOURCE_LOCK_PASS: independent MIT Noise C library; no ESPHome runtime. No build performed.')
