from pathlib import Path
import subprocess
import os
root = Path(__file__).resolve().parents[1]
profile = os.environ.get('OTBR_HOST_PROFILE', 'stable')
if profile not in ('stable', 'bbr'): raise SystemExit('Invalid Host profile')
build_tag = 'host-bbr-arm' if profile == 'bbr' else 'host-arm'

archive = root / 'build' / build_tag / 'vendor/noise-c/libnoise_c.a'
nm = root.parent / 'toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-nm'
output = subprocess.check_output([str(nm), '-g', '--defined-only', str(archive)], text=True)
symbols = {line.split()[-1] for line in output.splitlines() if line.split()}
for suffix in ['init', 'update', 'finish', 'auth', 'verify', 'power_on_self_test']:
    name = 'poly1305_' + suffix
    if name in symbols: raise SystemExit('Unnamespaced Noise symbol: ' + name)
if 'mi_noise_poly1305_init' not in symbols: raise SystemExit('Namespaced Poly1305 definition missing')
print('NOISE_SYMBOL_NAMESPACE_PASS')
