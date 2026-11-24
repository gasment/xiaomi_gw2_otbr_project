"""Read-only acceptance: no button/switch commands, Thread writes or local YAML."""
import asyncio
import ipaddress
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml
from aioesphomeapi import APIClient
from aioesphomeapi.model import ButtonInfo, SwitchInfo, TextSensorInfo

host = str(ipaddress.ip_address(sys.argv[1]))
with tempfile.TemporaryDirectory(prefix='gw2-entity-check-') as td:
    ssh = ['ssh', '-p', os.environ.get('OTBR_SSH_PORT', '2223'), '-oBatchMode=yes', '-oConnectTimeout=8',
           '-oStrictHostKeyChecking=accept-new', '-oUserKnownHostsFile=' + str(Path(td)/'known_hosts'), 'root@' + host]
    def read(command):
        return subprocess.check_output(ssh+[command], text=True, timeout=15)
    secret_text = read('if [ -f /data/otbr/secrets.yaml ]; then cat /data/otbr/secrets.yaml; else echo "{}"; fi')
    secrets = yaml.safe_load(secret_text) or {}
    class Loader(yaml.SafeLoader): pass
    Loader.add_constructor('!secret', lambda loader,node: secrets[loader.construct_scalar(node)])
    config = yaml.load(read('cat /data/otbr/config.yaml'), Loader=Loader)
    properties = dict(line.split('=',1) for line in read('cat /etc/build.prop').splitlines() if '=' in line)
    firmware = properties.get('ro.sys.mi_fw_ver', '')
    if properties.get('ro.sys.mi_build_num'): firmware += '_' + properties['ro.sys.mi_build_num']
    expected_uptime = float(read('cat /proc/uptime').split()[0])
    ipv4_addresses = set(re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)', read('ip -4 addr show')))
subs = config.get('substitutions', {})
def resolve(v):
    if isinstance(v,str):
        for _ in range(16):
            new = re.sub(r'\$\{([^}]+)\}', lambda m:str(subs[m[1]]),v)
            if new == v: break
            v = new
    return v
expected = {}
for kind in ('ipv4', 'uptime', 'reset', 'fw_ver', 'sys_led'):
    entry = config['thread_br'].get(kind)
    assert isinstance(entry,dict), 'Configure thread_br.' + kind + ' first'
    expected[kind] = resolve(entry.get('id',kind))

async def main():
    api_config = config.get('api', {})
    psk = resolve(api_config.get('encryption',{}).get('key'))
    client = APIClient(host, int(api_config.get('port',6053)), noise_psk=psk, provide_time=False)
    try:
        await client.connect(login=True)
        info = await client.device_info()
        assert info.manufacturer == 'Xiaomi' and info.model == 'mi_gateway2_otbr', 'Device identity metadata mismatch'
        assert not info.project_name and not info.project_version and not info.compilation_time, 'Legacy firmware suffix metadata'
        assert info.esphome_version == (Path(__file__).resolve().parents[3]/'VERSION').read_text().strip(), 'OTBR version mismatch'
        entities, _ = await client.list_entities_services()
        by_id = {e.object_id:e for e in entities}
        assert all(name in by_id for name in expected.values()), 'Some gateway entities are not advertised'
        selected = {kind:by_id[name] for kind,name in expected.items()}
        assert isinstance(selected['reset'],ButtonInfo) and selected['reset'].device_class == 'restart'
        assert isinstance(selected['sys_led'],SwitchInfo) and not selected['sys_led'].assumed_state
        assert all(isinstance(selected[k],TextSensorInfo) for k in ('ipv4','uptime','fw_ver'))
        states = {}; ready = asyncio.Event()
        required = {entity.key for kind,entity in selected.items() if kind != 'reset'}
        def on_state(state):
            if state.key not in required: return
            states[state.key] = state
            if all(key in states and not states[key].missing_state for key in required): ready.set()
        client.subscribe_states(on_state)
        await asyncio.wait_for(ready.wait(),60)
        def state(kind): return states[selected[kind].key].state
        assert state('ipv4') in ipv4_addresses, 'IPv4 does not match a real gateway address'
        assert state('fw_ver') == firmware, 'Firmware version is not the stock build.prop version'
        match = re.fullmatch(r'(\d+)d:(\d{2})h:(\d{2})m',state('uptime'))
        assert match and int(match[2]) < 24 and int(match[3]) < 60, 'Uptime format mismatch'
        seconds = int(match[1])*86400 + int(match[2])*3600 + int(match[3])*60
        assert abs(seconds-expected_uptime) <= 180, 'Uptime does not match Linux boot duration'
        print('GATEWAY_ENTITIES_READONLY_PASS: IPv4, Linux uptime, stock firmware, LED readback and restart button discovery')
        print('No button/switch command or Thread configuration sent. LED actuation and actual reboot require explicit manual testing.')
    finally:
        await client.disconnect()

if __name__ == '__main__': asyncio.run(main())
