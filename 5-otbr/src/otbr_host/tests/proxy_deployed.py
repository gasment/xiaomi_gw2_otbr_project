"""Read-only proxy management check. Does not claim the HA uplink consumer."""
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

host=str(ipaddress.ip_address(sys.argv[1]))
with tempfile.TemporaryDirectory(prefix='proxy-readonly-') as td:
    ssh=['ssh','-p',os.environ.get('OTBR_SSH_PORT','2223'),'-oBatchMode=yes','-oConnectTimeout=8',
         '-oStrictHostKeyChecking=accept-new','-oUserKnownHostsFile='+str(Path(td)/'known_hosts'),'root@'+host]
    def read(command):return subprocess.check_output(ssh+[command],text=True,timeout=15)
    secrets=yaml.safe_load(read('if [ -f /data/otbr/secrets.yaml ]; then cat /data/otbr/secrets.yaml; else echo "{}"; fi')) or {}
    class Loader(yaml.SafeLoader):pass
    Loader.add_constructor('!secret',lambda loader,node:secrets[loader.construct_scalar(node)])
    config=yaml.load(read('cat /data/otbr/config.yaml'),Loader=Loader)
proxy=config.get('thread_proxy_api')
if not isinstance(proxy,dict):raise SystemExit('Configure the top-level thread_proxy_api block on the gateway first.')
def resolve(value):
    if isinstance(value,str):
        for _ in range(16):
            new=re.sub(r'\$\{([^}]+)\}',lambda m:str(config.get('substitutions',{})[m[1]]),value)
            if new==value:break
            value=new
    return value
async def main():
    key=resolve(proxy.get('encryption',{}).get('key'))
    client=APIClient(host,int(proxy.get('port',6065)),noise_psk=key,provide_time=False)
    try:
        await client.connect(login=False)
        info=await client.device_info()
        assert info.manufacturer=='Xiaomi'
        assert info.esphome_version==(Path(__file__).resolve().parents[4]/'VERSION').read_text().strip()
        entities,services=await client.list_entities_services();assert not entities and not services
        seen=asyncio.Event();status={}
        def receive(call):
            if call.service not in ('thread_proxy.info','thread_proxy.status'):return
            data=dict(call.data)
            assert data.get('component')=='thread_proxy_api' and data.get('version')=='1'
            assert data.get('id')==info.mac_address.replace(':','').lower()
            assert data.get('uplink_protocol')=='tsd2-v1'
            status.update(data);seen.set()
        client.subscribe_service_calls(receive)
        await asyncio.wait_for(seen.wait(),10)
        print('PROXY_MANAGEMENT_PASS', 'ready='+status.get('data_plane_ready','false'),
              'role='+status.get('thread_role','unknown'),'nodes='+status.get('node_count','?'),
              'queued='+status.get('queue_size','?'))
        print('No uplink ownership, UDP probe, node packet, ACK or network configuration sent. Verify node-to-HA delivery separately.')
    finally:await client.disconnect(force=True)
if __name__=='__main__':asyncio.run(main())
