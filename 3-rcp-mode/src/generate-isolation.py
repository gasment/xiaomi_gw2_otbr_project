"""Rebuild narrow RCP isolation patches from verified stock 1.0.8_0015 scripts."""
from pathlib import Path
import hashlib
import subprocess
root = Path(__file__).resolve().parent
ref = root / 'references/stock-1.0.8_0015'
payload = root / 'rcp-mode-package/payload'
expected = {
    'fw_manager.sh': '29e515f12127e6d3efd6ce41e848aa6534cef7b1fef8400299d65db38c9ae641',
    'app_monitor.sh': '6a344dd2e54d7314039249de9dd901482d9e3351f8a65b7bfcfe983ebffb91b2',
}
for name, digest in expected.items():
    if hashlib.sha256((ref / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Unrecognized stock script: ' + name)
fw = (ref / 'fw_manager.sh').read_bytes().decode()
lines = fw.split('\n')
count = 0
for i, line in enumerate(lines):
    if line.lstrip().startswith(('mZ3GatewayHost_MQTT ', 'mzigbee_agent ', 'Z3GatewayHost_MQTT ')):
        lines[i] = '# RCP mode disabled: ' + line
        count += 1
assert count == 5, count
fw = '\n'.join(lines)
needle = 'coordinator_ota()\n{\n'
assert fw.count(needle) == 1
fw = fw.replace(needle, needle + '    echo "RCP mode: stock coordinator OTA skipped"\n    return 0\n', 1)
mon = (ref / 'app_monitor.sh').read_bytes().decode()
for name in ['mzigbee_agent       handler_mzigbee_agent_leaved', 'mZ3GatewayHost_MQTT handler_mZ3GatewayHost_MQTT_leaved']:
    lines = mon.splitlines(keepends=True)
    assert sum(name in line for line in lines) == 1
    mon = ''.join(line for line in lines if name not in line)
for name in ['handler_mzigbee_agent_leaved', 'handler_mZ3GatewayHost_MQTT_leaved']:
    needle = name + '()\n{\n'
    assert mon.count(needle) == 1
    mon = mon.replace(needle, needle + '    return 0 # RCP mode: do not restart stock Zigbee services\n', 1)
for name, text in [('fw_manager.sh', fw), ('app_monitor.sh', mon)]:
    (payload / name).write_bytes(text.encode())
    subprocess.run(['sh', '-n', str(payload / name)], check=True)
(payload / 'stock.sha256').write_text(''.join(digest + '  /bin/' + name + '\n' for name, digest in expected.items()))
manifest = payload / 'payload.sha256'
names = [line.split('  ', 1)[1] for line in manifest.read_text().splitlines() if line]
manifest.write_text(''.join(hashlib.sha256((payload / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names))
print('RCP_ISOLATION_0015_PATCH_PASS: five launch sites, coordinator OTA and two monitor handlers isolated')
