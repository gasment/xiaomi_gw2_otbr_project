"""Reject owned runtime YAML and obvious credential material; skip dependencies."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
ignored = {'vendor', 'build', 'downloads', '.git', '__pycache__'}
problems = []
jwt = re.compile(rb'eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}')
for path in root.rglob('*'):
    if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts): continue
    if path.suffix.lower() in ('.yaml', '.yml'):
        problems.append(path.relative_to(root).as_posix())
    elif path.stat().st_size <= 4 * 1024 * 1024:
        data = path.read_bytes()
        if jwt.search(data) or re.search(rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----', data):
            problems.append(path.relative_to(root).as_posix())
if problems:
    raise SystemExit('Project privacy check failed (values redacted): ' + ', '.join(problems))
print('PROJECT_PRIVACY_PASS: no owned runtime YAML, JWT or PEM private key in source.')
