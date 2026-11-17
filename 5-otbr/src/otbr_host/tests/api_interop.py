"""Interoperate with the real official aioesphomeapi client, not a mock codec.

The user starts this after building the C++ native target. No radio or HA config.
"""
import asyncio
import base64
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml
from aioesphomeapi import APIClient
from aioesphomeapi.model import ButtonInfo, SwitchInfo, TextSensorInfo
from aioesphomeapi.core import InvalidEncryptionKeyAPIError


async def exercise(port, key):
    def client(psk=key):
        return APIClient('127.0.0.1',port,noise_psk=psk,expected_name='mi-otbr-api-test',provide_time=False)
    expected={'rcp_connectivity','thread_identity','thread_role','neighbor_count','ipv4','uptime','fw_ver','reset','sys_led'}
    async def session():
        api=client()
        try:
            await asyncio.wait_for(api.connect(login=True),10)
            info=await api.device_info()
            assert info.name=='mi-otbr-api-test' and info.mac_address.lower()=='02:00:00:00:00:01'
            assert info.manufacturer == 'Xiaomi' and info.model == 'mi_gateway2_otbr'
            assert not info.project_name and not info.project_version and not info.compilation_time
            assert info.esphome_version == (Path(__file__).resolve().parents[4]/'VERSION').read_text().strip()
            entities,services=await api.list_entities_services()
            assert {e.object_id for e in entities}==expected and not services
            assert len({e.key for e in entities})==len(entities)
            by_id={e.object_id:e for e in entities}
            assert isinstance(by_id['reset'],ButtonInfo) and by_id['reset'].device_class=='restart'
            assert isinstance(by_id['sys_led'],SwitchInfo) and not by_id['sys_led'].assumed_state
            assert all(isinstance(by_id[k],TextSensorInfo) for k in ('ipv4','uptime','fw_ver'))
            states={};received=asyncio.Event()
            def on_state(state):
                states[state.key]=state
                if len(states)==len(expected)-1:received.set()  # Buttons have no state.
            api.subscribe_states(on_state)
            await asyncio.wait_for(received.wait(),5)
            assert all(s.missing_state for s in states.values()), 'Protocol-only server fabricated real state'
            assert by_id['reset'].key not in states, 'Button incorrectly emitted a text state'
            # This dedicated server records and REJECTS commands, with no OS backend.
            api.switch_command(by_id['sys_led'].key, True)
            api.switch_command(by_id['sys_led'].key, False)
            api.button_command(by_id['reset'].key)
            api.button_command(by_id['fw_ver'].key)  # Wrong-domain keys must not dispatch.
            api.switch_command(by_id['reset'].key, True)
            await api.device_info()  # Ordered roundtrip drains preceding commands.
            print('PASS: ' + ('Noise' if key else 'plaintext') + ' connection, device info, entity discovery and missing-state subscription')
            # Wait for the C++ server's independent 30-second ping, confirming
            # the official client responds and the session remains usable.
            await asyncio.sleep(32)
            assert (await api.device_info()).name=='mi-otbr-api-test'
            print('PASS: keepalive connection survived')
            return {e.object_id:e.key for e in entities}
        finally:await api.disconnect()
    keys=await session()
    if key is None:
        api=client()
        try:
            await api.connect(login=True)
            entities,_=await api.list_entities_services()
            assert {e.object_id:e.key for e in entities}==keys
            print('PASS: plaintext reconnect keeps stable entity keys')
        finally: await api.disconnect()
        return
    # A working positive control must precede this negative test. Requiring the
    # exact client error prevents generic handshake/network failures passing it.
    bad=client(base64.b64encode(secrets.token_bytes(32)).decode())
    try:
        try:
            await asyncio.wait_for(bad.connect(login=True,log_errors=False),10)
        except InvalidEncryptionKeyAPIError:
            print('PASS: invalid Noise PSK rejected as InvalidEncryptionKeyAPIError')
        else:
            raise AssertionError('Invalid Noise PSK accepted')
    finally:
        await bad.disconnect(force=True)
    api=client()
    try:
        await api.connect(login=True)
        entities,_=await api.list_entities_services()
        assert {e.object_id:e.key for e in entities}==keys
        print('PASS: reconnect keeps stable entity keys')
    finally:await api.disconnect()


async def main(binary, encrypted=True):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    key=base64.b64encode(secrets.token_bytes(32)).decode()
    with tempfile.TemporaryDirectory(prefix='mi-otbr-api-') as td:
        base=Path(td)
        config={
            'device':{'name':'mi-otbr-api-test','friendly_name':'Protocol Check','mac_address':'02:00:00:00:00:01'},
            'api':{'port':port,'encryption':{'key':key}},
            'thread_br':{
                'backbone':'auto','radio':'uart_rcp','rcp':{'device':'/dev/ttyS1','rcp_connectivity':{'id':'rcp_connectivity','name':'RCP Connectivity'}},
                'web':{'port':8080,'user':'test','passwd':'test-only'},
                'thread_network_config':{'channel':20,'network_name':'ProtocolTest','network_key':'00112233445566778899aabbccddeeff','pan_id':0x1234,'ext_pan_id':'0011223344556677','pskc':'00112233445566778899aabbccddeeff','mesh_local_prefix':'fd11:2233:4455:6677::/64'},
                'thread_identity':{'id':'thread_identity','name':'Thread ID'},
                'thread_role':{'id':'thread_role','name':'Thread Role'},
                'neighbor_count':{'id':'neighbor_count','name':'Neighbors'},
                'ipv4':{'name':'IPv4'}, 'uptime':{'name':'Gateway Uptime'},
                'fw_ver':{'name':'Gateway Firmware'}, 'reset':{'name':'Restart Gateway'},
                'sys_led':{'name':'System LED'},
            },
        }
        cfg=base/'config.yaml';cfg.write_text(yaml.safe_dump(config,sort_keys=False));cfg.chmod(0o600)
        if not encrypted:
            config['api'].pop('encryption')
            cfg.write_text(yaml.safe_dump(config,sort_keys=False))
        with open(base/'server.log','w') as log:
            process=subprocess.Popen([str(binary),str(cfg)],stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('Protocol server exited before listening')
                try:
                    reader,writer=await asyncio.open_connection('127.0.0.1',port)
                    writer.close();await writer.wait_closed();break
                except OSError:await asyncio.sleep(.05)
            else:raise RuntimeError('Protocol server did not listen')
            # Malformed oversized handshake must not affect other sessions.
            reader,writer=await asyncio.open_connection('127.0.0.1',port)
            writer.write(b'\x01\xff\xff' if encrypted else b'\x00\x81\x20');await writer.drain()
            assert await asyncio.wait_for(reader.read(1),3)==b''
            writer.close();await writer.wait_closed()
            print('PASS: oversized handshake rejected')
            await exercise(port,key if encrypted else None)
            log_text=(base/'server.log').read_text()
            assert log_text.count('PROTOCOL_ONLY_COMMAND_REJECTED sys_led on')==1
            assert log_text.count('PROTOCOL_ONLY_COMMAND_REJECTED sys_led off')==1
            assert log_text.count('PROTOCOL_ONLY_COMMAND_REJECTED reset off')==1
            assert log_text.count('PROTOCOL_ONLY_COMMAND_REJECTED')==3, 'Wrong-domain command dispatched'
            print('PASS: switch/button domain discovery, missing switch state, exact-key command dispatch; no OS control')
            print('NATIVE_API_INTEROP_PASS (official aioesphomeapi; no UART, OTBR or real Dataset)')
        except Exception:
            # Server logs contain no PSK or YAML body; do not print config.
            print((base/'server.log').read_text(),file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:process.wait(timeout=12)
            except subprocess.TimeoutExpired:process.kill();process.wait()

async def both(binary):
    await main(binary)
    await main(binary, encrypted=False)

if __name__=='__main__':asyncio.run(both(Path(sys.argv[1]).resolve()))
