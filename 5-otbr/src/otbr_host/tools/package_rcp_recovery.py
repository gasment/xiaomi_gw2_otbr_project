"""Build a scripts-only update; never compile, read device YAML or include a Host binary."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
compatibility = json.loads((root / 'recovery/compatibility.json').read_text())
for name in ('common.sh', 'start.sh', 'stop.sh'):
    actual = hashlib.sha256((root / 'deploy/payload' / name).read_bytes()).hexdigest()
    if actual != compatibility['/data/otbr/' + name]:
        raise SystemExit('Update compatibility metadata before packaging changed ' + name)
subprocess.run(['python3', str(root / 'tests/rcp_recovery.py')], check=True)
subprocess.run(['python3', str(root / 'tests/rcp_recovery_update.py')], check=True)
with tempfile.TemporaryDirectory(prefix='otbr-recovery-package-') as directory:
    stage = Path(directory) / 'rcp-recovery-update'
    stage.mkdir(mode=0o700)
    (stage / 'payload').mkdir()
    for name in ('supervisor.sh', 'rcp-recovery.sh', 'status.sh'):
        shutil.copy2(root / 'deploy/payload' / name, stage / 'payload' / name)
    for name in ('install.sh', 'rollback.sh', 'README.md'):
        shutil.copy2(root / 'recovery' / name, stage / name)
    (stage / 'compatibility.sha256').write_text(''.join(
        digest + '  ' + path + '\n' for path, digest in compatibility.items() if path != '/data/otbr/supervisor.sh'))
    supervisor_hash = hashlib.sha256((stage / 'payload/supervisor.sh').read_bytes()).hexdigest()
    (stage / 'accepted-supervisor.sha256').write_text(compatibility['/data/otbr/supervisor.sh'] + '\n' + supervisor_hash + '\n')
    for path in stage.rglob('*.sh'):
        path.chmod(0o700)
        subprocess.run(['sh', '-n', str(path)], check=True)
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    assert not any(p.name in ('config.yaml', 'secrets.yaml', 'mi-otbr-host') for p in files)
    (stage / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(stage).as_posix() + '\n' for p in files))
    archive = root / 'rcp-recovery-update.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        output.add(stage, arcname='rcp-recovery-update')
    archive.chmod(0o600)
    (root / 'rcp-recovery-update.tar.gz.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
print('RCP_RECOVERY_SCRIPTS_PACKAGE_READY:', archive)
print('No compilation, binary replacement, gateway connection, GPIO operation or service restart was performed.')
