"""GET-only BBR inspection, reading gateway-owned credentials into memory only."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen
import yaml
root=Path(__file__).resolve().parents[1]
host=sys.argv[1]
(root/'build').mkdir(exist_ok=True)
ssh=['ssh','-p',os.environ.get('OTBR_SSH_PORT','2223'),'-oBatchMode=yes','-oConnectTimeout=8',
     '-oStrictHostKeyChecking=accept-new','-oUserKnownHostsFile='+str(root/'build/gateway_known_hosts'),'root@'+host]
private=subprocess.check_output(ssh+['if [ -f /data/otbr/secrets.yaml ]; then cat /data/otbr/secrets.yaml; else printf "{}\\n"; fi'],text=True)
secrets=yaml.safe_load(private) or {}
class Loader(yaml.SafeLoader): pass
Loader.add_constructor('!secret',lambda loader,node:secrets[loader.construct_scalar(node)])
config=yaml.load(subprocess.check_output(ssh+['cat /data/otbr/config.yaml'],text=True),Loader=Loader)
def value(v):
    if isinstance(v,str) and v.startswith('${') and v.endswith('}'): return value(config.get('substitutions',{})[v[2:-1]])
    return v
web=config['thread_br']['web']
auth=base64.b64encode((str(value(web['user']))+':'+str(value(web['passwd']))).encode()).decode()
request=Request('http://'+host+':'+str(web.get('port',8080))+'/bbr',headers={'Authorization':'Basic '+auth})
try:
    with urlopen(request,timeout=8) as response: body=json.load(response)
except Exception:
    raise SystemExit('BBR_STATUS_UNAVAILABLE: confirm the new program is installed and Web is reachable.') from None
if body.get('error')!=0: raise SystemExit('BBR_STATUS_ERROR')
state=body['result']
print(json.dumps(state,ensure_ascii=False,indent=2))
if state.get('backend')!='userspace-af-packet': raise SystemExit('BBR_BACKEND_NOT_ENABLED: stable profile remains installed.')
if state.get('state')=='secondary':
    print('BBR_SECONDARY_OBSERVED: another Primary BBR owns multicast forwarding; local forwarding is intentionally idle.')
elif state.get('state')=='primary':
    if not state.get('forwarder_ready'): raise SystemExit('BBR_PRIMARY_TRANSPORT_NOT_READY: inspect packet socket/filter logs.')
    print('BBR_PRIMARY_TRANSPORT_READY: packet taps opened. This GET-only check cannot determine end-to-end multicast reception; use the two endpoint logs.')
else: raise SystemExit('BBR_DISABLED: inspect Thread attachment and packet backend capability logs.')
print('Only a GET request was sent; no Primary election override, listener registration or test packet was sent.')
