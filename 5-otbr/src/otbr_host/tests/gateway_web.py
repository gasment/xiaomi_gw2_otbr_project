"""User-run, read-only Web acceptance against the no-attach gateway bundle."""
import base64
import gzip
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import yaml

root = Path(__file__).resolve().parents[1]
from gateway_test_data import noattach_secrets, noattach_text
secrets = noattach_secrets()
base = os.environ.get('OTBR_TEST_WEB_URL', 'http://GATEWAY_ADDRESS:18080').rstrip('/')
auth = 'Basic ' + base64.b64encode(('test:' + secrets['web_password']).encode()).decode()
def get(path, authenticated=True):
    req = Request(base + path, headers={'Authorization': auth} if authenticated else {})
    try:
        response = urlopen(req, timeout=8)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()
def data(path):
    status, _, body = get(path)
    assert status == 200, (path, status)
    return json.loads(body)
for path in ['/', '/get_properties', '/srp']:
    assert get(path, False)[0] == 401, 'Unauthenticated access: ' + path
status, headers, body = get('/')
assert status == 200 and headers.get('Content-Encoding') == 'gzip'
assert gzip.decompress(body) == (root / 'web/frontend/index.html').read_bytes()
properties = data('/get_properties')
assert properties['error'] == 0
assert properties['result']['Thread:Role'] == 'disabled'
assert properties['result']['RCP:Version'].startswith('SL-OPENTHREAD/2.5.3.0_GitHub-1fceb225b')
assert data('/node/state') == 'disabled'
node = data('/node_information')
assert node['error'] == 0 and node['result']['State'] == 0
addresses = data('/ipaddr')
assert addresses['error'] == 0 and isinstance(addresses['result'], list)
assert all('address' in a and 'prefixLength' in a for a in addresses['result'])
srp = data('/srp')
assert srp['error'] == 0 and srp['result']['state'] in ['running', 'stopped', 'disabled']
assert isinstance(srp['result']['hosts'], list)
class ConfigLoader(yaml.SafeLoader):
    pass
ConfigLoader.add_constructor('!secret', lambda loader, node: loader.construct_scalar(node))
config = yaml.load(noattach_text('config.yaml'), Loader=ConfigLoader)
commissioner_enabled = config['thread_br'].get('commissioner', {}).get('enabled', False)
assert get('/commissioner')[0] == (200 if commissioner_enabled else 404)
print('HOST_NOATTACH_WEB_PASS')
print('Basic auth, embedded page, real RCP status, disabled Thread, IPv6 addresses and SRP queries passed.')
print('No POST, diagnostics scan, Dataset import or Thread configuration was requested.')
