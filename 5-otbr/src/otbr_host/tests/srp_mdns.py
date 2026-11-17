"""LAN SRP->mDNS check with exact records and gateway response attribution."""
import argparse
import ipaddress
import re
import socket
import time
from zeroconf import DNSIncoming, DNSOutgoing, DNSQuestion

SERVICE_TYPE = '_esphomelib._tcp.local.'


def matching_records(records, name, address, port):
    service = (name + '.' + SERVICE_TYPE).lower()
    hostname = (name + '.local.').lower()
    matches = set()
    for record in records:
        if record.ttl <= 0:
            continue
        key = record.name.lower()
        if record.type == 12 and key == SERVICE_TYPE and record.alias.lower() == service:
            matches.add('PTR')
        elif record.type == 33 and key == service and record.server.lower() == hostname and record.port == port:
            matches.add('SRV')
        elif record.type == 16 and key == service and record.text:
            matches.add('TXT')
        elif record.type == 28 and key == hostname and ipaddress.ip_address(record.address) == address:
            matches.add('AAAA')
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', default='GATEWAY_ADDRESS', help='gateway LAN IPv4 used for response attribution')
    parser.add_argument('--name', required=True, help='registered node host/service instance label')
    parser.add_argument('--address', required=True, help='node IPv6 from the current SRP table')
    parser.add_argument('--port', type=int, default=6053, help='node Native API service port, not the SRP server port')
    parser.add_argument('--timeout', type=int, default=20)
    args = parser.parse_args()
    try:
        gateway = str(ipaddress.IPv4Address(args.gateway))
        address = ipaddress.IPv6Address(args.address)
    except ValueError:
        parser.error('expected a gateway LAN IPv4 and node IPv6 address')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', args.name):
        parser.error('--name must be a single DNS hostname label')
    if not 1 <= args.port <= 65535 or not 1 <= args.timeout <= 180:
        parser.error('invalid service port or timeout')
    service = args.name + '.' + SERVICE_TYPE
    hostname = args.name + '.local.'
    query = DNSOutgoing(0, multicast=True)
    for name, kind in ((SERVICE_TYPE, 12), (service, 33), (service, 16), (hostname, 28)):
        query.add_question(DNSQuestion(name, kind, 0x8001))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((gateway, 5353))
            local = route.getsockname()[0]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('', 5353))
            listener.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                socket.inet_aton('224.0.0.251') + socket.inet_aton(local))
            listener.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local))
            listener.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            listener.settimeout(.5)
            print('LAN_MDNS_QUERY: local=' + local + ' required_responder=' + gateway + ':5353', flush=True)
            print('Service: ' + service + ' expected_port=' + str(args.port) + ' expected_AAAA=' + str(address), flush=True)
            deadline, last_send = time.monotonic() + args.timeout, 0
            found = set()
            while time.monotonic() < deadline:
                if time.monotonic() - last_send >= 2:
                    for packet in query.packets():
                        listener.sendto(packet, ('224.0.0.251', 5353))
                    last_send = time.monotonic()
                try:
                    packet, peer = listener.recvfrom(65535)
                except socket.timeout:
                    continue
                if peer != (gateway, 5353):
                    continue
                response = DNSIncoming(packet, source=peer)
                if not response.valid or not response.flags & 0x8000:
                    continue
                matched = matching_records(response.answers(), args.name, address, args.port)
                added = matched - found
                found |= matched
                if added:
                    print('GATEWAY_RESPONSE: source=' + gateway + ':5353 records=' + ','.join(sorted(added)), flush=True)
                if found == {'PTR', 'SRV', 'TXT', 'AAAA'}:
                    print('SRP_LAN_MDNS_PUBLICATION_PASS')
                    print('Gateway answered discovery PTR, SRV target/port, nonempty TXT and the exact registered node AAAA.')
                    print('No service control, node connection, restart, registration or configuration change was performed.')
                    return 0
            print('SRP_LAN_MDNS_NOT_VERIFIED: missing_from_gateway=' + ','.join(sorted({'PTR', 'SRV', 'TXT', 'AAAA'} - found)))
            print('Check current SRP registration and LAN multicast reachability. Answers from other BRs do not satisfy this check.')
            return 1
    except OSError as error:
        print('SRP_LAN_MDNS_SOCKET_FAILED: ' + type(error).__name__)
        print('Run on the LAN or a WSL network mode that can receive LAN multicast; no success conclusion.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
