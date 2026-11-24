"""Resolve a real ESPHome discovery advertisement from the LAN; no radio access."""
import asyncio
import ipaddress
import re
import sys
from pathlib import Path
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

TYPE = '_esphomelib._tcp.local.'

async def main(host, port):
    target = ipaddress.ip_address(host)
    pending = set()
    def changed(zeroconf, service_type, name, state_change):
        if state_change != ServiceStateChange.Removed and len(pending) < 64:
            pending.add(name)
    azc = AsyncZeroconf()
    browser = AsyncServiceBrowser(azc.zeroconf, [TYPE], handlers=[changed])
    try:
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            for name in list(pending):
                pending.discard(name)
                info = AsyncServiceInfo(TYPE, name)
                if not await info.async_request(azc.zeroconf, 1500): continue
                addresses = {ipaddress.ip_address(a) for a in info.parsed_addresses()}
                if target not in addresses or info.port != port: continue
                props = {k.decode(errors='replace'): (v or b'').decode(errors='replace')
                         for k, v in info.properties.items()}
                assert re.fullmatch(r'[0-9a-fA-F]{12}', props.get('mac', '')), 'Missing stable MAC TXT'
                assert 'project_name' not in props and 'project_version' not in props, 'Legacy project metadata advertised'
                assert props.get('version') == (Path(__file__).resolve().parents[3]/'VERSION').read_text().strip(), 'OTBR version mismatch'
                assert props.get('network') in ('wifi', 'ethernet'), 'Missing backbone TXT'
                encryption = props.get('api_encryption')
                assert encryption in (None, 'Noise_NNpsk0_25519_ChaChaPoly_SHA256'), 'Unexpected encryption TXT'
                assert 'api_provisioning' not in props, 'Unsupported key provisioning advertised'
                print('MDNS_DISCOVERY_PASS')
                print('Service:', name)
                print('Target:', info.server, 'port=' + str(info.port))
                print('MAC:', props['mac'], 'network=' + props['network'],
                      'encryption=' + ('Noise' if encryption else 'plaintext'))
                return
            await asyncio.sleep(.2)
        raise SystemExit('MDNS_DISCOVERY_TIMEOUT: no matching A/AAAA + SRV + TXT record; check same-LAN multicast reachability.')
    finally:
        await browser.async_cancel()
        await azc.async_close()

if __name__ == '__main__': asyncio.run(main(sys.argv[1], int(sys.argv[2])))
