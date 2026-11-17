"""Access the running Host CLI through temporary SSH forwarding; no gateway install."""
import argparse
import os
import ipaddress
from pathlib import Path
import re
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', default=os.environ.get('OTBR_TEST_HOST', 'GATEWAY_ADDRESS'))
    parser.add_argument('--ssh-port', type=int, default=2223)
    parser.add_argument('--interface', default='wpan0')
    parser.add_argument('command', nargs='+', help='OpenThread CLI words; setters change runtime state')
    args = parser.parse_args()
    try: host = str(ipaddress.ip_address(args.gateway))
    except ValueError: parser.error('gateway must be an IP address')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', args.interface): parser.error('invalid interface name')
    if not 1 <= args.ssh_port <= 65535: parser.error('invalid SSH port')
    if any(not word or re.search(r'[\x00-\x20\\\x7f]', word) for word in args.command):
        parser.error('CLI words must not contain whitespace, backslashes or control characters')
    command = ' '.join(args.command).encode()
    if len(command) > 500: parser.error('CLI command too long')
    root = Path(__file__).resolve().parents[1]
    (root / 'build').mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    ssh = ['ssh', '-p', str(args.ssh_port), '-oBatchMode=yes', '-oConnectTimeout=8',
           '-oExitOnForwardFailure=yes', '-oStrictHostKeyChecking=accept-new',
           '-oUserKnownHostsFile=' + str(root / 'build/gateway_known_hosts'),
           '-N', '-L', '127.0.0.1:' + str(port) + ':/var/run/openthread-' + args.interface + '.sock', 'root@' + host]
    process = subprocess.Popen(ssh, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 12
        while True:
            try:
                session = socket.create_connection(('127.0.0.1', port), timeout=2)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('SSH CLI forwarding unavailable')
                time.sleep(.1)
        with session:
            session.settimeout(8)
            session.sendall(command)
            data = b''
            while len(data) < 65536:
                block = session.recv(4096)
                if not block: break
                data += block
                if b'Done\r\n' in data or b'Error ' in data: break
        print(data.decode(errors='replace'), end='', flush=True)
        return 0 if b'Done\r\n' in data and b'Error ' not in data else 1
    except (OSError, RuntimeError):
        print('CLI_REQUEST_FAILED: check gateway SSH and the running Host socket.')
        return 1
    finally:
        process.terminate()
        try: process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        process.stderr.close()


if __name__ == '__main__':
    raise SystemExit(main())
