from pathlib import Path
import hashlib
import json
root = Path(__file__).resolve().parents[1]
lock = json.loads((root / 'deps.lock.json').read_text())['openssl-arm']
for name, digest in lock['files'].items():
    path = root / lock['path'] / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('Static OpenSSL dependency changed: ' + name)
print('RELEASE_TLS_LOCK_PASS')
