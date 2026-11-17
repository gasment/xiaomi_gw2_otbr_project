"""Run routing apply/restore against fake proc files, never real sysctls."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='otbr-routing-test-') as directory:
    tmp = Path(directory)
    conf = tmp / 'proc'; conf.mkdir()
    original = {}
    for interface in ['all', 'default', 'lo', 'wlan0', 'eth0']:
        (conf / interface).mkdir()
        for field, value in [('forwarding', '0\n'), ('accept_ra', '1\n'), ('disable_ipv6', '1\n' if interface == 'eth0' else '0\n')]:
            # Match gateway proc reads: selected files have no trailing newline.
            if interface in ('all', 'wlan0'): value = value.rstrip('\n')
            path = conf / interface / field; path.write_text(value); original[path] = value
    script = (root / 'deploy/payload/routing.sh').read_text()
    script = script.replace('/proc/sys/net/ipv6/conf', str(conf)).replace('/tmp/mi-otbr-routing.before', str(tmp / 'routing.before'))
    path = tmp / 'routing.sh'; path.write_text(script)
    subprocess.run(['sh', str(path), 'apply'], check=True)
    assert (conf / 'all/forwarding').read_text() == '1\n'
    assert (conf / 'wlan0/accept_ra').read_text() == '2\n'
    assert (conf / 'eth0/disable_ipv6').read_text() == '0\n'
    subprocess.run(['sh', str(path), 'apply'], check=True)  # Must keep the original snapshot.
    subprocess.run(['sh', str(path), 'restore'], check=True)
    assert all(p.read_text().strip() == content.strip() for p, content in original.items())
    assert not (tmp / 'routing.before').exists()
    subprocess.run(['sh', str(path), 'restore'], check=True)
print('DEPLOY_ROUTING_RESTORE_PASS (fake proc files only)')
with tempfile.TemporaryDirectory(prefix='otbr-yaml-owner-test-') as directory:
    tmp = Path(directory)
    for name in ['config.yaml', 'secrets.yaml']:
        (tmp / (name + '.example')).write_text('example for ' + name)
    (tmp / 'config.yaml.example').write_text('api: !secret api_key\n')
    script = (root / 'deploy/payload/init-config.sh').read_text().replace('/data/otbr', str(tmp))
    path = tmp / 'init.sh'; path.write_text(script)
    subprocess.run(['sh', str(path)], check=True, capture_output=True)
    (tmp / 'config.yaml').write_text('USER_EDITED_GATEWAY_CONFIG')
    (tmp / 'secrets.yaml').write_text('USER_EDITED_GATEWAY_SECRETS')
    for name in ['config.yaml', 'secrets.yaml']: (tmp / (name + '.example')).write_text('NEW_RELEASE_EXAMPLE')
    subprocess.run(['sh', str(path)], check=True, capture_output=True)
    assert (tmp / 'config.yaml').read_text() == 'USER_EDITED_GATEWAY_CONFIG'
    assert (tmp / 'secrets.yaml').read_text() == 'USER_EDITED_GATEWAY_SECRETS'
    (tmp / 'secrets.yaml').unlink()
    subprocess.run(['sh', str(path)], check=True, capture_output=True)
    assert not (tmp / 'secrets.yaml').exists(), 'Inline user config unexpectedly recreated a secret sidecar'
print('GATEWAY_YAML_PRESERVATION_PASS (first install creates; upgrade preserves edited files)')
