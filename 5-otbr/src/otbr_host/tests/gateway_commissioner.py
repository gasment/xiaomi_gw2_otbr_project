"""User-run no-attach test: status plus requests that must be rejected.

No successful start, cancellation, Dataset write or radio configuration request.
"""
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import yaml

root = Path(__file__).resolve().parents[1]
from gateway_test_data import noattach_secrets
secrets = noattach_secrets()
base = os.environ.get('OTBR_TEST_WEB_URL', 'http://GATEWAY_ADDRESS:18080').rstrip('/')
auth = 'Basic ' + base64.b64encode(('test:' + secrets['web_password']).encode()).decode()
def request(path, body=None, authenticated=True):
    headers = {'Authorization': auth} if authenticated else {}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(base + path, headers=headers, data=body)
    try:
        response = urlopen(req, timeout=8)
    except HTTPError as error:
        response = error
    with response:
        payload = response.read()
        return response.status, json.loads(payload)
def status():
    code, data = request('/commissioner/api/status')
    assert code == 200 and data['error'] == 0
    assert data['enabled'] is True and data['attached'] is False
    assert data['dataset_matches'] is False and data['busy'] is False
    assert data['phase'] == 'idle' and data['remaining_s'] == 0
    assert isinstance(data['network'], dict) and isinstance(data['candidates'], list)
    assert data['commissioner_id'] == 'mi-gateway2-noattach-test'
    return data
assert request('/commissioner/api/status', authenticated=False)[0] == 401
status()
print('PASS: authenticated Commissioner status; disabled Thread cannot commission')
for body in [b'{', b'[]', b'{"action":"start","unexpected":1}', b'{"action":"start","action":"cancel"}', b'{"action":5}', b'{"action":"start\\u0000cancel"}']:
    code, data = request('/commissioner/api/control', body)
    assert code == 400 and data['error'] != 0, (body, code)
    status()
print('PASS: malformed, duplicate, unknown and incorrectly typed fields rejected')
body = json.dumps({'action': 'start', 'pskd': 'TEST1234', 'eui64': '', 'candidate': '', 'timeout_s': 10}).encode()
code, data = request('/commissioner/api/control', body)
assert code == 409 and data['error'] != 0
status()
assert request('/node/state')[1] == 'disabled'
print('HOST_NOATTACH_COMMISSIONER_PASS')
print('Valid start request was rejected while unattached; no commissioning window or Thread network was started.')
print('Actual petition, Joiner discovery and successful commissioning remain untested.')
