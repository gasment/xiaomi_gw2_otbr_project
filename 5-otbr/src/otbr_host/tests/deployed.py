"""Read active configuration from the gateway via SSH; never use a local YAML copy."""
import asyncio
import base64
import ipaddress
import json
from pathlib import Path
import sys
import os
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import yaml
from aioesphomeapi import APIClient

root = Path(__file__).resolve().parents[1]
host = sys.argv[1]
(root / 'build').mkdir(exist_ok=True)
ssh = ['ssh', '-p', os.environ.get('OTBR_SSH_PORT', '2223'), '-oBatchMode=yes', '-oConnectTimeout=8',
       '-oStrictHostKeyChecking=accept-new', '-oUserKnownHostsFile=' + str(root / 'build/gateway_known_hosts'), 'root@' + host]
try:
    secret_text = subprocess.check_output(ssh + ['if [ -f /data/otbr/secrets.yaml ]; then cat /data/otbr/secrets.yaml; else printf "{}\\n"; fi'], text=True)
    config_text = subprocess.check_output(ssh + ['cat /data/otbr/config.yaml'], text=True)
except subprocess.CalledProcessError:
    raise SystemExit('Cannot read gateway YAML using existing SSH on port 2223; no local fallback used.')
secrets = yaml.safe_load(secret_text) or {}
class Loader(yaml.SafeLoader): pass
Loader.add_constructor('!secret', lambda loader, node: secrets[loader.construct_scalar(node)])
config = yaml.load(config_text, Loader=Loader)
subs = config.get('substitutions', {})
def text(v):
    if isinstance(v, str) and v.startswith('${') and v.endswith('}'): return subs[v[2:-1]]
    return v
br = config['thread_br']; web = br['web']; net = br['thread_network_config']
auth = 'Basic ' + base64.b64encode((str(text(web['user'])) + ':' + str(text(web['passwd']))).encode()).decode()
base = 'http://' + host + ':' + str(web.get('port', 8080))
def request(path, body=None, timeout=8):
    headers = {'Authorization': auth}
    data = None if body is None else json.dumps(body).encode()
    if body is not None: headers['Content-Type'] = 'application/json'
    try: response = urlopen(Request(base + path, data=data, headers=headers), timeout=timeout)
    except HTTPError as error: response = error
    with response: return response.status, json.loads(response.read())
def hex_value(value, count):
    if isinstance(value, int): return format(value, '0' + str(count * 2) + 'x')
    return str(value).lower().removeprefix('0x').zfill(count * 2)
deadline = time.monotonic() + 180
while True:
    try:
        code, role = request('/node/state')
        if code == 200 and role in ['child', 'router', 'leader']: break
    except (OSError, URLError): pass
    if time.monotonic() >= deadline: raise SystemExit('DEPLOY_ATTACH_TIMEOUT: inspect /var/log/mi-otbr.log and supervisor log.')
    time.sleep(2)
code, active = request('/node/dataset/active')
assert code == 200 and active['NetworkName'] == net['network_name'], 'Dataset name mismatch'
for field, key, count in [('ExtPanId', 'ext_pan_id', 8), ('NetworkKey', 'network_key', 16), ('PSKc', 'pskc', 16)]:
    assert active[field] == hex_value(net[key], count), 'Dataset field mismatch: ' + field
assert active['Channel'] == net['channel'] and active['PanId'] == net['pan_id'], 'Dataset channel/PAN mismatch'
assert ipaddress.ip_network(active['MeshLocalPrefix']) == ipaddress.ip_network(net['mesh_local_prefix'])
print('PASS: Thread attached with configured Dataset; role=' + role)
# POSIX delegates ICMP echo replies to Linux. Self-Ping can terminate
# in the kernel instead of returning to OpenThread. Test a responding peer.
code, topology = request('/topology', timeout=40)
assert code in [200, 206] and topology.get('error') == 0 and topology.get('result'), 'No actual topology responses; HTTP=' + str(code)
print('PASS: actual diagnostic responses; nodes=' + str(len(topology['result'])) + '; partial=' + str(code == 206))
code, node = request('/node')
assert code == 200 and 'Rloc16' in node and 'RlocAddress' in node, 'Cannot obtain current local RLOC'
peers = sorted({entry['Rloc16'] for entry in topology['result']
                if isinstance(entry, dict) and isinstance(entry.get('Rloc16'), int)
                and 0 <= entry['Rloc16'] <= 0xfbff and (entry['Rloc16'] & 0x3ff) == 0
                and entry['Rloc16'] != node['Rloc16']})
if not peers:
    raise SystemExit('DEPLOY_NO_REMOTE_PING_TARGET: topology has no other responding Router; remote Ping remains unverified.')
leader = (node.get('LeaderData') or {}).get('LeaderRouterId')
leader_rloc = leader << 10 if isinstance(leader, int) and 0 <= leader <= 62 else None
peer = leader_rloc if leader_rloc in peers else peers[0]
local = ipaddress.IPv6Address(node['RlocAddress'])
target = str(ipaddress.IPv6Address(local.packed[:-2] + peer.to_bytes(2, 'big')))
code, ping = request('/ping', {'address': target, 'count': 3, 'size': 32}, timeout=20)
stats = ping.get('result', {}).get('statistics', {}) if isinstance(ping.get('result'), dict) else {}
print('Remote Ping: target=' + target + ' HTTP=' + str(code) + ' error=' + str(ping.get('error'))
      + ' sent=' + str(stats.get('sent', '?')) + ' received=' + str(stats.get('received', '?'))
      + ' loss_percent=' + str(stats.get('loss_percent', '?')))
if code != 200 or ping.get('error') != 0 or stats.get('received', 0) < 1:
    print('Ping message:', str(ping.get('message', ''))[:160])
    raise SystemExit('DEPLOY_REMOTE_PING_FAILED: remote Router did not return a reply; inspect Host ICMP logs.')
print('PASS: remote Thread Router Ping, real OpenThread callback and statistics')
async def api_check():
    api_config = config.get('api') or {}
    encryption = api_config.get('encryption')
    api = APIClient(host, api_config.get('port', 6053), noise_psk=text(encryption['key']) if encryption else None, expected_name=config['device']['name'], provide_time=False)
    try:
        await asyncio.wait_for(api.connect(login=True), 15)
        info = await api.device_info()
        assert info.name == config['device']['name'] and info.webserver_port == web.get('port', 8080)
        entities, _ = await api.list_entities_services()
        identity = br.get('thread_identity', {}).get('id', 'thread_identity')
        match = next((e for e in entities if e.object_id == identity), None)
        if match:
            ready = asyncio.Event()
            def on_state(state):
                if state.key == match.key and not state.missing_state and str(state.state).startswith('ot1:'): ready.set()
            api.subscribe_states(on_state)
            await asyncio.wait_for(ready.wait(), 60)
        print('PASS: ' + ('encrypted' if encryption else 'plaintext') + ' Native API, configured identity/entities and Web port')
    finally: await api.disconnect()
asyncio.run(api_check())
print('HA:', request('/ha/status')[1]['result']['status'])
code, node = request('/node')
if node.get('NumOfRouter', 0) < 2 and len(topology['result']) < 2:
    print('NOTICE: no other router proved reachable; existing-network RF connectivity still needs another node response.')
    if role == 'leader': raise SystemExit('DEPLOY_ATTACHED_WITHOUT_PEER_PROOF: local functions work, but existing-network connectivity is not yet proved.')
print('DEPLOY_THREAD_ACCEPTANCE_PASS')
print('LAN-to-remote-Thread routing and real Joiner commissioning still require an actual peer/device test.')
