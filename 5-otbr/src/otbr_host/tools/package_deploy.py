"""Package code and examples only. The gateway exclusively owns runtime YAML."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
profile = os.environ.get('OTBR_HOST_PROFILE', 'stable')
if profile not in ('stable', 'bbr'): raise SystemExit('Invalid Host profile')
build_tag = 'host-bbr-arm' if profile == 'bbr' else 'host-arm'

binary = root / 'build' / build_tag / 'mi-otbr-host'
if len(sys.argv) != 1: raise SystemExit('No config argument: runtime YAML belongs on the gateway.')
if not binary.is_file(): raise SystemExit('Build the ARM Host first: sh build-release.sh')
version = (root.parents[1] / 'VERSION').read_text().strip()
binary_data = binary.read_bytes()
if b'OTBR_HOST_VERSION=' + version.encode() not in binary_data or b'THREAD_PROXY_RUNTIME_ENABLED' not in binary_data:
    raise SystemExit('Host binary is older than current VERSION or lacks the built-in proxy; rebuild before packaging.')
if b'YAML_RUNTIME_DEPLOY_READY' not in binary.read_bytes():
    raise SystemExit('Runtime executable predates deployment/HA integration; rebuild.')
if profile == 'bbr' and b'BBR_BACKEND=userspace-af-packet' not in binary.read_bytes():
    raise SystemExit('BBR package requires userspace backend binary; rebuild bbr profile.')
prefix = root.parent / 'toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-'
header = subprocess.check_output([str(prefix) + 'readelf', '-h', str(binary)], text=True)
program = subprocess.check_output([str(prefix) + 'readelf', '-l', str(binary)], text=True)
dynamic = subprocess.check_output([str(prefix) + 'readelf', '-d', str(binary)], text=True)
if 'ELF32' not in header or 'ARM' not in header or 'INTERP' in program or '(NEEDED)' in dynamic:
    raise SystemExit('Runtime is not static ARM32.')
archive = root / ('otbr-deploy-bbr.tar.gz' if profile == 'bbr' else 'otbr-deploy.tar.gz')
dest = root / ('otbr-deploy-bbr' if profile == 'bbr' else 'otbr-deploy')
with tempfile.TemporaryDirectory(prefix='release-', dir=root / 'build') as temporary:
    stage = Path(temporary) / 'otbr-deploy'
    shutil.copytree(root / 'deploy', stage)
    stage.chmod(0o700)
    payload = stage / 'payload'
    shutil.copy2(binary, payload / 'mi-otbr-host')
    subprocess.run([str(prefix) + 'strip', str(payload / 'mi-otbr-host')], check=True)
    assert not (payload / 'config.yaml').exists() and not (payload / 'secrets.yaml').exists()
    (stage / 'certs').mkdir()
    ca = Path('/etc/ssl/certs/ca-certificates.crt')
    if not ca.is_file(): raise SystemExit('TLS CA bundle missing.')
    shutil.copy2(ca, stage / 'certs/ca-certificates.crt')
    licenses = {
      'OTBR': root / 'vendor/ot-br-posix/LICENSE',
      'OpenThread': root / 'vendor/ot-br-posix/third_party/openthread/repo/LICENSE',
      'mbedTLS': root / 'vendor/ot-br-posix/third_party/openthread/repo/third_party/mbedtls/repo/LICENSE',
      'Noise-C': root / 'vendor/noise-c/LICENSE', 'yaml-cpp': root / 'vendor/yaml-cpp/LICENSE',
      'cJSON': root / 'vendor/ot-br-posix/third_party/cJSON/repo/LICENSE',
      'cpp-httplib': root / 'vendor/ot-br-posix/third_party/cpp-httplib/repo/LICENSE',
      'Web': root / 'licenses/LICENSE.espressif',
      'OpenSSL': root.parent / 'deps/openssl-arm/LICENSE.txt',
    }
    if not licenses['OpenSSL'].is_file(): licenses['OpenSSL'] = root / 'licenses/LICENSE.openssl'
    (stage / 'licenses').mkdir()
    for name, path in licenses.items():
      if not path.is_file(): raise SystemExit('Missing license: ' + name)
      shutil.copy2(path, stage / 'licenses' / (name + '-LICENSE'))
    shutil.copy2(root / 'deps.lock.json', stage / 'deps.lock.json')
    shutil.copy2(root / 'THREAD-PROXY.md', stage / 'THREAD-PROXY.md')
    shutil.copy2(root.parents[1] / 'VERSION', stage / 'VERSION')
    for p in stage.rglob('*.sh'):
      p.chmod(0o700); subprocess.run(['sh', '-n', str(p)], check=True)
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    if any(p.name in ('config.yaml', 'secrets.yaml') for p in files):
      raise SystemExit('Runtime YAML must not be included in the generic program package.')
    (stage / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(stage).as_posix() + '\n' for p in files))
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=stage, check=True)
    with tempfile.NamedTemporaryFile(prefix='otbr-release-', suffix='.tar.gz', dir=root, delete=False) as stream:
      name = stream.name
      with tarfile.open(fileobj=stream, mode='w:gz') as tf: tf.add(stage, arcname='otbr-deploy')
    if dest.is_symlink() or not dest.resolve().is_relative_to(root.resolve()): raise SystemExit('Invalid package destination')
    if (dest / 'payload').is_symlink(): raise SystemExit('Package payload destination must not be a symlink')
    for obsolete in [dest / 'payload/config.yaml', dest / 'payload/secrets.yaml']:
      if obsolete.is_file() or obsolete.is_symlink(): obsolete.unlink()
    shutil.copytree(stage, dest, dirs_exist_ok=True); dest.chmod(0o700)
    os.replace(name, archive); archive.chmod(0o600)
print('DEPLOY_PACKAGE_READY:', archive)
print('Program and examples only; no runtime YAML or private secrets included. Gateway files are preserved on upgrade.')
