"""Official aioesphomeapi interop; synthetic node, no OT/UDP/radio/gateway."""
import asyncio
import base64
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml
from aioesphomeapi import APIClient
from aioesphomeapi.core import InvalidEncryptionKeyAPIError

async def exercise(binary, encrypted):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='gw2-proxy-') as td:
        root = Path(td)
        config = {
            'device': {'name': 'proxy-protocol-test', 'mac_address': '02:00:00:00:00:01'},
            'api': {'port': port + 1 if port < 65535 else port - 1},
            'thread_br': {
                'rcp': {'device': '/dev/ttyS1'},
                'web': {'port': 8080, 'user': 'test', 'passwd': 'test-only'},
                'thread_network_config': {
                    'channel': 20, 'network_name': 'ProxyTest',
                    'network_key': '00112233445566778899aabbccddeeff', 'pan_id': 0x1234,
                    'ext_pan_id': '0011223344556677', 'pskc': '00112233445566778899aabbccddeeff',
                    'mesh_local_prefix': 'fd11:2233:4455:6677::/64'}},
            'thread_proxy_api': {
                'port': port, 'status_interval': '1s',
                'udp': {'encryption': {'key': base64.b64encode(secrets.token_bytes(32)).decode()}}}}
        key = base64.b64encode(secrets.token_bytes(32)).decode() if encrypted else None
        if key: config['thread_proxy_api']['encryption'] = {'key': key}
        cfg = root/'config.yaml'; cfg.write_text(yaml.safe_dump(config)); cfg.chmod(0o600)
        with (root/'server.log').open('w') as log:
            process = subprocess.Popen([str(binary), str(cfg), '--fixture'], stdout=log, stderr=log)
        client = None
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError('Proxy test server exited: ' + (root/'server.log').read_text())
                try:
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    writer.close(); await writer.wait_closed(); break
                except OSError: await asyncio.sleep(.05)
            else: raise AssertionError('Proxy listener timeout')
            if key:
                bad = APIClient('127.0.0.1', port, noise_psk=base64.b64encode(secrets.token_bytes(32)).decode(), provide_time=False)
                try:
                    try: await bad.connect(login=False, log_errors=False)
                    except InvalidEncryptionKeyAPIError: pass
                    else: raise AssertionError('Wrong proxy key accepted')
                finally: await bad.disconnect(force=True)
            client = APIClient('127.0.0.1', port, noise_psk=key, provide_time=False)
            await client.connect(login=False)
            info = await client.device_info(); assert info.manufacturer == 'Xiaomi'
            assert info.esphome_version == (Path(__file__).resolve().parents[3]/'VERSION').read_text().strip()
            entities, services = await client.list_entities_services()
            assert not entities and not services
            metadata = asyncio.Event(); received = asyncio.Event(); empty = asyncio.Event()
            chunks = {}; deliveries = []
            def receive(call):
                data = dict(call.data)
                if call.service in ('thread_proxy.info', 'thread_proxy.status'):
                    assert data['component'] == 'thread_proxy_api' and data['version'] == '1' and data['id'] == '020000000001'
                    assert data['uplink_protocol'] == 'tsd2-v1' and data['data_plane_ready'] == 'true'
                    if data['queue_size'] == '0': empty.set()
                    metadata.set()
                if call.service == 'thread_proxy.packet':
                    assert data['mac'] == '020000000002' and data['kind'] == '2' and data['flags'] == '3'
                    assert len(data['payload']) <= 512
                    chunks[int(data['part'])] = base64.b64decode(data['payload'], validate=True)
                    if len(chunks) == int(data['parts']):
                        body = b''.join(chunks[i] for i in range(len(chunks))); chunks.clear()
                        offset = 0; types = []
                        while offset < len(body):
                            typ, size = struct.unpack_from('!HH', body, offset)
                            types.append(typ); offset += 4 + size
                        assert offset == len(body) and types == [10, 19, 16000]
                        deliveries.append(data['delivery']); received.set()
            client.subscribe_service_calls(receive)
            await asyncio.wait_for(metadata.wait(), 5)
            client.send_home_assistant_state('thread_proxy.uplink', None, 'tsd2-v1')
            await asyncio.wait_for(received.wait(), 5); received.clear()
            await asyncio.wait_for(received.wait(), 8)
            assert deliveries[0] == deliveries[1], 'Retry changed delivery token'
            empty.clear()
            client.send_home_assistant_state('thread_proxy.delivery_ack', None, deliveries[-1])
            await asyncio.wait_for(empty.wait(), 5)
            print('PROXY_INTEROP_PASS', 'Noise' if encrypted else 'plaintext',
                  'metadata, independent key, fragmented raw packet, retry token, HA ACK')
        finally:
            if client: await client.disconnect(force=True)
            process.terminate()
            try: process.wait(timeout=12)
            except subprocess.TimeoutExpired: process.kill(); process.wait()

async def main(binary):
    await exercise(binary, False)
    await exercise(binary, True)
if __name__ == '__main__': asyncio.run(main(Path(sys.argv[1]).resolve()))
