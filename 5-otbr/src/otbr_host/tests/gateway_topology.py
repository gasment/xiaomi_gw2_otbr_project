"""No-attach endpoint validation; must not send diagnostic messages."""
import base64
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import yaml
root = Path(__file__).resolve().parents[1]
from gateway_test_data import noattach_secrets
secrets = noattach_secrets()
base = os.environ.get('OTBR_TEST_WEB_URL', 'http://GATEWAY_ADDRESS:18080').rstrip('/')
auth = 'Basic ' + base64.b64encode(('test:' + secrets['web_password']).encode()).decode()
def request(path, authenticated=True, data=None):
    req = Request(base + path, headers={'Authorization': auth} if authenticated else {}, data=data)
    try:
        response = urlopen(req, timeout=8)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())
assert request('/node/state')[1] == 'disabled'
for path in ['/topology', '/diagnostics']:
    assert request(path, False)[0] == 401
    started = time.monotonic()
    code, body = request(path)
    assert code == 409 and body['error'] == 409 and body['result'] is None
    assert time.monotonic() - started < 5, 'Unattached request waited for a scan'
    assert request(path, data=b'{}')[0] == 405
assert request('/node/state')[1] == 'disabled'
assert request('/commissioner/api/status')[1]['busy'] is False
print('HOST_NOATTACH_TOPOLOGY_PASS')
print('Authentication and GET-only checks passed; unattached scans rejected without diagnostic requests.')
print('No fabricated empty topology; real multi-node collection and route/child details remain untested.')
