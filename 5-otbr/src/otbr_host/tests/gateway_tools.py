"""No-attach validation: read Dataset and reject Ping without enabling Thread."""
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
        return response.status, json.loads(response.read())
assert request('/node/state')[1] == 'disabled'
assert request('/node/dataset/active', authenticated=False)[0] == 401
code, dataset = request('/node/dataset/active')
assert code in [200, 404] and isinstance(dataset, dict)
if code == 404:
    assert dataset['error'] == 404
    print('PASS: absent Active Dataset reports 404; no YAML substitution')
else:
    assert 'error' not in dataset
    print('PASS: Active Dataset JSON read (credentials are not printed)')
assert request('/ping', b'{}', authenticated=False)[0] == 401
invalid = [b'{', b'[]', b'{}', b'{"address":"invalid"}',
           b'{"address":"::1","address":"::2"}', b'{"address":"::1","count":1.5}',
           b'{"address":"::1","count":0}', b'{"address":"::1","count":11}',
           b'{"address":"::1","size":513}', b'{"address":"::1","size":"32"}',
           b'{"address":"::1","unknown":1}']
for body in invalid:
    code, data = request('/ping', body)
    assert code == 400 and data['error'] != 0, (body, code)
print('PASS: malformed, duplicate, unknown and out-of-range Ping fields rejected')
code, data = request('/ping', b'{"address":"::1","count":1,"size":32}')
assert code == 409 and data['error'] != 0
assert request('/node/state')[1] == 'disabled'
print('HOST_NOATTACH_TOOLS_PASS')
print('Valid Ping rejected while unattached; no ICMP request, Dataset import or Thread enable requested.')
print('Actual Ping replies, loss statistics and routing remain untested.')
