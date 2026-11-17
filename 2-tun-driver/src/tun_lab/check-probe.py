from pathlib import Path
import struct

LAB = Path(__file__).resolve().parent
def parse(path):
    b = path.read_bytes()
    if b[:6] != b"\x7fELF\x01\x01":
        raise SystemExit('Expected ELF32 little-endian: ' + str(path))
    e = struct.unpack_from('<16sHHIIIIIHHHHHH', b)
    if e[2] != 40: raise SystemExit('Expected ARM ELF')
    ss = [struct.unpack_from('<IIIIIIIIII', b, e[6]+i*e[11]) for i in range(e[12])]
    def data(s): return b[s[4]:s[4]+s[5]]
    def name(st, i): return st[i:].split(b'\0', 1)[0].decode()
    sn = data(ss[e[13]])
    sections = {name(sn,s[0]): s for s in ss}
    symbols = []
    for s in ss:
        if s[1] != 2: continue
        st = data(ss[s[6]])
        for i in range(0, s[5], s[9]):
            a = struct.unpack_from('<IIIBBH', b, s[4]+i)
            symbols.append((name(st,a[0]), a))
    offsets = {}
    rel = sections.get('.rel.gnu.linkonce.this_module')
    if rel:
        for i in range(0, rel[5], rel[9]):
            offset, info = struct.unpack_from('<II', b, rel[4]+i)
            offsets[symbols[info>>8][0]] = offset
    layout = (sections['.gnu.linkonce.this_module'][5], offsets.get('init_module'), offsets.get('cleanup_module'))
    constants = {}
    for n,a in symbols:
        if n.startswith('mg_') and a[2] == 4 and 0 < a[5] < len(ss):
            constants[n] = struct.unpack_from('<I', b, ss[a[5]][4]+a[1])[0]
    mi = data(sections['.modinfo']).split(b'\0')
    vm = next(x.decode() for x in mi if x.startswith(b'vermagic='))
    return layout, constants, vm

reference = LAB.parent/'origin_ko/ccm.ko'
probe = LAB/'probe/mg_abi_probe.ko'
ref_layout, _, ref_vm = parse(reference)
layout, constants, vm = parse(probe)
lines = ['Reference: '+str(reference.relative_to(LAB.parent)), 'Candidate: '+str(probe.relative_to(LAB.parent)), ref_vm, vm,
         'Reference module size/init/exit: '+str(tuple(hex(x) for x in ref_layout)),
         'Candidate module size/init/exit: '+str(tuple(hex(x) for x in layout))]
lines += [n+' = '+hex(v)+' ('+str(v)+')' for n,v in sorted(constants.items())]
ok = layout == ref_layout and vm == ref_vm
lines.append('MODULE_ABI_BASELINE_MATCH' if ok else 'MODULE_ABI_BASELINE_MISMATCH')
lines.append('This only checks basic module ABI, not all network structure layouts or runtime safety.')
report = '\n'.join(lines)+'\n'
print(report)
(LAB/'probe-report.txt').write_text(report)
raise SystemExit(0 if ok else 1)
