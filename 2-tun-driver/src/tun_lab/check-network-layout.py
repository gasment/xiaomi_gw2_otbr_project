from pathlib import Path
import re
lab = Path(__file__).resolve().parent
text = (lab/'probe-report.txt').read_text()
measurements = {m.group(1): int(m.group(2),16) for m in re.finditer(r'^(mg_\w+) = (0x[0-9a-f]+)', text, re.M)}
size = measurements['mg_sizeof_net_device']
private_offset = (size+31) & ~31
expected = {
    'mg_netdev_tx_offset': 0x280,
    'mg_skb_data_offset': 0xa8,
    'mg_skb_head_offset': 0xa4,
    'mg_skb_len_offset': 0x5c,
    'mg_skb_dev_offset': 0x14,
    'mg_skb_mac_header_offset': 0x9a,
}
lines = [
    'Original bridge.ko netdev_priv offset: 0x540',
    'Candidate sizeof(net_device): '+hex(size),
    'Candidate netdev_priv offset (ALIGN32): '+hex(private_offset),
]
ok = private_offset == 0x540
for name, target in expected.items():
    actual = measurements.get(name)
    match = actual == target
    ok = ok and match
    lines.append(name+': original='+hex(target)+' candidate='+(hex(actual) if actual is not None else 'missing')+' '+('MATCH' if match else 'MISMATCH'))
lines += [
    'NETWORK_LAYOUT_ANCHOR_MATCH' if ok else 'NETWORK_LAYOUT_ANCHOR_MISMATCH',
    'These anchors are inferred from stock bridge.ko. They do not prove every field or runtime safety.',
    'No module has been loaded. Review results before TUN runtime tests.',
]
report='\n'.join(lines)+'\n'
print(report)
(lab/'network-layout-report.txt').write_text(report)
raise SystemExit(0 if ok else 1)
