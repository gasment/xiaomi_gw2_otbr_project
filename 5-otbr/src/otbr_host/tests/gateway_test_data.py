"""Read legacy no-attach test data from the gateway, never persist it in project."""
from pathlib import Path
import os
import subprocess
import yaml
root = Path(__file__).resolve().parents[1]
def noattach_text(name, host=None):
    if name not in ('config.yaml', 'secrets.yaml'): raise ValueError('Invalid test filename')
    (root / 'build').mkdir(exist_ok=True)
    target = host or os.environ.get('OTBR_TEST_HOST', 'GATEWAY_ADDRESS')
    command = ['ssh', '-p', os.environ.get('OTBR_SSH_PORT', '2223'), '-oBatchMode=yes', '-oConnectTimeout=8',
               '-oStrictHostKeyChecking=accept-new', '-oUserKnownHostsFile=' + str(root / 'build/gateway_known_hosts'),
               'root@' + target, 'cat /tmp/host-noattach-probe/' + name]
    return subprocess.check_output(command, text=True)
def noattach_secrets(host=None):
    return yaml.safe_load(noattach_text('secrets.yaml', host))
