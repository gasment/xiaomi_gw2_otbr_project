"""Package a user-built read-only kernel query; no runtime YAML or gateway access."""
from pathlib import Path
import hashlib
import os
import subprocess
import tarfile
import tempfile
root=Path(__file__).resolve().parents[1]
binary=root/'build/bbr-probe-arm/bbr-kernel-probe'
readelf=root.parent/'toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-readelf'
if not binary.is_file(): raise SystemExit('Run sh build-bbr-probe.sh first')
header=subprocess.check_output([str(readelf),'-h',str(binary)],text=True)
if 'ELF32' not in header or not any('Machine:' in line and 'ARM' in line for line in header.splitlines()):
    raise SystemExit('Expected ELF32 ARM probe')
if 'INTERP' in subprocess.check_output([str(readelf),'-l',str(binary)],text=True):
    raise SystemExit('Probe unexpectedly needs a dynamic interpreter')
if '(NEEDED)' in subprocess.check_output([str(readelf),'-d',str(binary)],text=True):
    raise SystemExit('Probe unexpectedly needs a shared library')
items={'bbr-kernel-probe':binary.read_bytes(),'probe.sh':(root/'bbr/probe.sh').read_bytes(),
       'README.md':(root/'bbr/README.md').read_bytes()}
with tempfile.TemporaryDirectory(prefix='bbr-query-package-') as directory:
    stage=Path(directory)/'bbr-kernel-probe'; stage.mkdir()
    for name,data in items.items():
        p=stage/name; p.write_bytes(data); p.chmod(0o700 if name!='README.md' else 0o600)
    (stage/'SHA256SUMS').write_text(''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(items.items())))
    subprocess.run(['sh','-n',str(stage/'probe.sh')],check=True)
    fd,name=tempfile.mkstemp(prefix='bbr-query-',suffix='.tar.gz',dir=root)
    os.close(fd)
    try:
        with tarfile.open(name,'w:gz') as tf: tf.add(stage,arcname='bbr-kernel-probe')
        dest=root/'bbr-kernel-probe.tar.gz'
        if dest.is_symlink(): raise SystemExit('Refusing symlink package destination')
        os.replace(name,dest)
    finally:
        if os.path.exists(name): os.unlink(name)
print('BBR_KERNEL_QUERY_PACKAGE_READY:',dest)
