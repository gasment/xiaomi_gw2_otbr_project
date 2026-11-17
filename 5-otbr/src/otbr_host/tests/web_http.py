"""User-run HTTP transport interop; standard library, no radio/backend."""
import base64
import gzip
import json
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
binary = root / 'build/web-native/otbr-web-http-check'
if not binary.is_file():
    raise SystemExit('Run sh build-web.sh first')
with tempfile.TemporaryDirectory(prefix='otbr-web-check-') as directory:
    tmp = Path(directory)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    config = (root / 'runtime-tests/noattach/config.example').read_text()
    config = config.replace('port: 18080', 'port: ' + str(port))
    config = config.replace('enabled: true', 'enabled: false')
    (tmp / 'config.yaml').write_text(config)
    password = secrets.token_urlsafe(24)
    (tmp / 'secrets.yaml').write_text('api_key: "' + base64.b64encode(secrets.token_bytes(32)).decode() + '"\nweb_password: "' + password + '"\n')
    auth = 'Basic ' + base64.b64encode(('test:' + password).encode()).decode()
    def request(path, authorization=auth, data=None):
        headers = {} if authorization is None else {'Authorization': authorization}
        req = Request('http://127.0.0.1:' + str(port) + path, headers=headers, data=data)
        try:
            response = urlopen(req, timeout=7)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()
    with (tmp / 'server.log').open('w+') as log:
        process = subprocess.Popen([str(binary), str(tmp / 'config.yaml')], stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), .1): break
                except OSError:
                    if process.poll() is not None:
                        log.seek(0); raise AssertionError(log.read())
                    time.sleep(.05)
            else:
                raise AssertionError('Web listener startup timeout')
            for path in ['/', '/static/api.js', '/get_properties']:
                for credential in [None, 'Basic invalid']:
                    status, headers, _ = request(path, credential)
                    assert status == 401 and headers.get('WWW-Authenticate', '').startswith('Basic ')
            print('PASS: pages, assets and API require Basic authentication')
            for asset in (root / 'web/frontend').rglob('*'):
                if not asset.is_file() or 'commissioner' in asset.name or asset.name.endswith(':Zone.Identifier'):
                    continue
                path = '/' + asset.relative_to(root / 'web/frontend').as_posix()
                status, headers, body = request(path)
                assert status == 200 and headers['Content-Encoding'] == 'gzip'
                if asset.suffix == '.png':
                    assert headers['Content-Type'] == 'image/png'
                assert gzip.decompress(body) == asset.read_bytes()
                assert headers['Cache-Control'] == 'no-store'
            assert request('/')[0] == 200
            assert request('/commissioner')[0] == 404
            print('PASS: embedded assets match source; disabled Commissioner is hidden')
            status, _, body = request('/get_properties')
            assert status == 503 and json.loads(body)['result'] is None
            assert request('/ping', data=b'{}')[0] == 503
            print('PASS: transport check does not invent OTBR data or execute controls')
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                raise AssertionError('Web server failed to stop within eight seconds')
        assert process.returncode == 0
        print('WEB_HTTP_TRANSPORT_PASS (no UART or Thread operations)')
