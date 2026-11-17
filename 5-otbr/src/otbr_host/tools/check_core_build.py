"""Check the baseline output after a user-initiated build."""
import json
from pathlib import Path
import subprocess
import sys

build = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
root = Path(__file__).resolve().parent.parent
prefix = root.parent / 'toolchains/armv7-musl/bin/arm-buildroot-linux-musleabihf-'
readelf = str(prefix) + 'readelf' if mode == 'arm' else 'readelf'
files = {}
for name in ['otbr-agent', 'ot-ctl']:
    matches = [p for p in build.rglob(name) if p.is_file() and 'CMakeFiles' not in p.parts]
    if len(matches) != 1:
        raise SystemExit('Cannot uniquely locate ' + name)
    path = matches[0]
    header = subprocess.check_output([readelf, '-h', str(path)], text=True)
    program = subprocess.check_output([readelf, '-l', str(path)], text=True)
    if mode == 'arm':
        if 'ARM' not in header or 'ELF32' not in header:
            raise SystemExit('Unexpected architecture: ' + name)
        if 'INTERP' in program:
            raise SystemExit('Dynamic interpreter present in static ARM build: ' + name)
        dynamic = subprocess.check_output([readelf, '-d', str(path)], text=True)
        if '(NEEDED)' in dynamic:
            raise SystemExit('Dynamic dependency in ARM build: ' + name)
    files[name] = str(path)
cache = (build / 'CMakeCache.txt').read_text()
for option in ['OTBR_DBUS', 'OTBR_WEB', 'OTBR_REST', 'OTBR_OPENWRT', 'OTBR_TREL', 'OTBR_NFTABLES', 'OT_FIREWALL']:
    if not any(line.startswith(option + ':') and line.endswith('=OFF') for line in cache.splitlines()):
        raise SystemExit('Expected disabled dependency/feature: ' + option)
if 'HAVE_LIBSYSTEMD' in ''.join(p.read_text(errors='replace') for p in build.rglob('flags.make')):
    raise SystemExit('Unexpected systemd dependency in baseline build.')
(build / 'verified-output.json').write_text(json.dumps(files, indent=2) + '\n')
print('CORE_BUILD_STATIC_CHECK_PASS')
for name, path in files.items():print(name + ': ' + path)
print('No binary was run. Radio protocol and Linux 4.9 runtime remain untested.')
