"""Local HA contract test, never contacts the user's HA or gateway."""
import base64
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading

root = Path(__file__).resolve().parents[1]
rows = [
    ['ot1:0011223344556677:8899aabbccddeeff:1000', 'Router Name', 'ha-router'],
    ['ot1:0011223344556677:1111111111111111:1034', 'Conflict One', 'ha-one'],
    ['ot1:0011223344556677:2222222222222222:1034', 'Conflict Two', 'ha-two'],
    ['ot1:0011223344556677:3333333333333333:1035', 'Child Name', 'ha-child'],
]
class Handler(http.server.BaseHTTPRequestHandler):
    mode = 'valid'
    requests = 0
    def log_message(self, *_): pass
    def do_POST(self):
        Handler.requests += 1
        assert self.path == '/ha/api/template'
        assert self.headers['Authorization'] == 'Bearer PRIVATE_TEST_TOKEN'
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert 'ot1:' in body['template'] and 'device_attr' in body['template']
        response = json.dumps(rows).encode()
        if self.mode == 'oversized': response = b' ' * 65537
        if self.mode == 'malformed': response = b'[["bad-id","name","device"]]'
        self.send_response(302 if self.mode == 'redirect' else 200)
        if self.mode == 'redirect': self.send_header('Location', '/must-not-follow')
        self.send_header('Content-Length', str(len(response))); self.end_headers()
        try: self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
try:
    with tempfile.TemporaryDirectory(prefix='ha-contract-') as directory:
        tmp = Path(directory)
        config = (root / 'runtime-tests/noattach/config.example').read_text()
        config = config.replace('  id: thread_br_main', '  id: thread_br_main\n  ha_url: http://127.0.0.1:' + str(server.server_port) + '/ha/\n  ha_token: !secret ha_token')
        (tmp / 'config.yaml').write_text(config)
        (tmp / 'secrets.yaml').write_text('api_key: "' + base64.b64encode(bytes(range(1,33))).decode() + '"\nweb_password: PRIVATE_WEB_PASSWORD\nha_token: PRIVATE_TEST_TOKEN\n')
        for mode in ['valid', 'malformed', 'oversized', 'redirect']:
            Handler.mode = mode; before = Handler.requests
            result = subprocess.run([str(root / 'build/web-native/ha-client-check'), str(tmp / 'config.yaml')], capture_output=True, text=True, timeout=12)
            assert 'PRIVATE_TEST_TOKEN' not in result.stdout + result.stderr
            assert Handler.requests == before + 1, 'Unexpected redirect or retry'
            if mode == 'valid':
                assert result.returncode == 0, result.stderr
                nodes = json.loads(result.stdout)
                assert nodes[0]['NodeName'] == 'Router Name'
                assert nodes[0]['ChildTable'][0]['NodeName'] == ''
                assert nodes[0]['ChildTable'][1]['NodeName'] == 'Child Name'
            else:
                assert result.returncode != 0, mode
        print('HA_HTTP_CONTRACT_PASS: base path/auth, identity matching, conflicting RLOC rejection, response cap and no redirects.')
finally:
    server.shutdown(); server.server_close(); thread.join()
