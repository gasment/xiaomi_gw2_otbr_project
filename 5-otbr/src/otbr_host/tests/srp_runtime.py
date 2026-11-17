"""GET-only SRP observation; gateway credentials remain in process memory."""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import yaml


class SrpQueryError(Exception):
    def __init__(self, code, retryable=True):
        super().__init__(code)
        self.retryable = retryable


def query_srp(url, auth):
    try:
        with urlopen(Request(url, headers={'Authorization': auth}), timeout=8) as response:
            body = json.load(response)
    except HTTPError as error:
        raise SrpQueryError('HTTP_' + str(error.code), error.code in (408, 429, 500, 502, 503, 504)) from None
    except URLError as error:
        raise SrpQueryError('NETWORK_' + type(error.reason).__name__) from None
    except OSError as error:
        raise SrpQueryError('NETWORK_' + type(error).__name__) from None
    except ValueError:
        raise SrpQueryError('INVALID_JSON') from None
    if not isinstance(body, dict) or body.get('error') != 0 or not isinstance(body.get('result'), dict):
        raise SrpQueryError('INVALID_API_RESULT')
    result = body['result']
    if 'state' not in result or 'port' not in result or not isinstance(result.get('hosts'), list):
        raise SrpQueryError('INVALID_SRP_SCHEMA')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', default='GATEWAY_ADDRESS')
    parser.add_argument('--expect-host', help='SRP hostname, with or without its domain suffix')
    parser.add_argument('--expect-port', type=int, help='fail clearly if the server no longer uses the node target port')
    parser.add_argument('--wait', type=int, default=0, help='observation seconds; default is one GET')
    args = parser.parse_args()
    try:
        address = ipaddress.ip_address(args.gateway)
    except ValueError:
        parser.error('--gateway must be an IP address')
    if not 0 <= args.wait <= 1800:
        parser.error('--wait must be between 0 and 1800 seconds')
    if args.wait and not args.expect_host:
        parser.error('--wait requires --expect-host')
    if args.expect_port is not None and not 1 <= args.expect_port <= 65535:
        parser.error('--expect-port must be between 1 and 65535')
    root = Path(__file__).resolve().parents[1]
    (root / 'build').mkdir(exist_ok=True)
    ssh = ['ssh', '-p', os.environ.get('OTBR_SSH_PORT', '2223'), '-oBatchMode=yes',
           '-oConnectTimeout=8', '-oStrictHostKeyChecking=accept-new',
           '-oUserKnownHostsFile=' + str(root / 'build/gateway_known_hosts'), 'root@' + str(address)]
    try:
        private = subprocess.check_output(ssh + ['if [ -f /data/otbr/secrets.yaml ]; then cat /data/otbr/secrets.yaml; else printf "{}\\n"; fi'], text=True, timeout=15)
        secrets = yaml.safe_load(private) or {}
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor('!secret', lambda loader, node: secrets[loader.construct_scalar(node)])
        config = yaml.load(subprocess.check_output(ssh + ['cat /data/otbr/config.yaml'], text=True, timeout=15), Loader=Loader)
        def resolve(value):
            for _ in range(24):
                if not (isinstance(value, str) and value.startswith('${') and value.endswith('}')):
                    return value
                value = config.get('substitutions', {})[value[2:-1]]
            raise ValueError('substitution cycle')
        web = config['thread_br']['web']
        auth = 'Basic ' + base64.b64encode((str(resolve(web['user'])) + ':' + str(resolve(web['passwd']))).encode()).decode()
        host = '[' + str(address) + ']' if address.version == 6 else str(address)
        url = 'http://' + host + ':' + str(web.get('port', 8080)) + '/srp'
    except Exception:
        raise SystemExit('SRP_CONFIG_READ_FAILED: check gateway SSH and runtime YAML; private input was not printed.') from None

    expected = (args.expect_host or '').lower().rstrip('.')
    deadline = time.monotonic() + args.wait
    first = True
    last_summary = None
    last_port = None
    failures = 0
    while True:
        try:
            result = query_srp(url, auth)
            if failures:
                print('SRP_QUERY_RECOVERED: transient failures=' + str(failures), flush=True)
                failures = 0
            state, port = result['state'], result['port']
            if last_port is not None and last_port != port:
                print('SRP_PORT_CHANGED: previous=' + str(last_port) + ' current=' + str(port)
                      + '; verify the node target after Host/server restart.', flush=True)
            last_port = port
            if first:
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            summary = (state, port, json.dumps(result.get('hosts', []), sort_keys=True))
            if summary != last_summary:
                print('SRP_STATE: state=' + str(state) + ' port=' + str(port), flush=True)
                last_summary = summary
            if state != 'running' or not isinstance(port, int) or not 0 < port <= 65535:
                print('SRP_NOT_SERVING: this gateway is not accepting SRP registrations. Client absence does not explain this state.', flush=True)
                print('Do not reflash the node yet. Inspect SRP/Network Data selection in this multi-BR network; Primary BBR is a separate role.')
                return 2
            if args.expect_port is not None and port != args.expect_port:
                print('SRP_TARGET_PORT_MISMATCH: node_expected=' + str(args.expect_port) + ' server_current=' + str(port)
                      + '; update the node target or deliberately restore the expected server port.')
                return 5
            if not expected:
                print('SRP_LISTENING_OBSERVED: server is running; client registration and LAN publication remain unverified.')
                return 0
            for entry in result.get('hosts', []):
                name = str(entry.get('name', '')).lower().rstrip('.')
                if entry.get('deleted') or not (name == expected or name.split('.')[0] == expected):
                    continue
                services = [s for s in entry.get('services', []) if not s.get('deleted')
                            and (str(s.get('type', '')).rstrip('.') == '_esphomelib._tcp'
                                 or str(s.get('type', '')).startswith('_esphomelib._tcp.'))
                            and s.get('port') == 6053]
                if entry.get('addresses') and services:
                    print('SRP_REGISTRATION_' + ('PRESENT' if first else 'OBSERVED') + ': host=' + name
                          + ' service=_esphomelib._tcp port=6053', flush=True)
                    print('This is the selected Xiaomi gateway registration table. An existing entry does not prove a fresh registration; LAN mDNS publication remains unverified.')
                    return 0
            if first:
                print('WAITING_FOR_HOST: ' + expected + '; now restart the existing C6 node and retain its SRP logs.', flush=True)
            if time.monotonic() >= deadline:
                print('SRP_REGISTRATION_NOT_OBSERVED: check the node SRP result and selected server; another BR may own its registration.')
                if result.get('truncated'):
                    print('The registration table is truncated; absence here is inconclusive.')
                return 3
            first = False
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        except SrpQueryError as error:
            failures += 1
            print('SRP_QUERY_FAILED: reason=' + str(error) + ' consecutive=' + str(failures), flush=True)
            if not error.retryable or not args.wait or time.monotonic() >= deadline:
                print('No success conclusion. Check Host/supervisor logs; authentication errors are not retried.')
                return 4
            print('SRP_QUERY_RETRY: observing until the original deadline; no device operation.', flush=True)
            time.sleep(min(2, max(0, deadline - time.monotonic())))


if __name__ == '__main__':
    raise SystemExit(main())
