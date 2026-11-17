from pathlib import Path
import hashlib
import re
import struct

LAB=Path(__file__).resolve().parent
def elf(path):
    b=path.read_bytes()
    if b[:6] != b"\x7fELF\x01\x01": raise SystemExit('Expected ELF32 little-endian')
    e=struct.unpack_from('<16sHHIIIIIHHHHHH',b)
    if e[2] != 40: raise SystemExit('Expected ARM ELF')
    ss=[struct.unpack_from('<IIIIIIIIII',b,e[6]+i*e[11]) for i in range(e[12])]
    def data(s): return b[s[4]:s[4]+s[5]]
    def name(st,i): return st[i:].split(b'\0',1)[0].decode()
    sn=data(ss[e[13]])
    sections={name(sn,s[0]):s for s in ss}
    syms=[]
    for s in ss:
        if s[1]!=2: continue
        st=data(ss[s[6]])
        for j in range(0,s[5],s[9]):
            a=struct.unpack_from('<IIIBBH',b,s[4]+j)
            syms.append((name(st,a[0]),a))
    rel=sections.get('.rel.gnu.linkonce.this_module')
    offsets={}
    if rel:
        for j in range(0,rel[5],rel[9]):
            off,info=struct.unpack_from('<II',b,rel[4]+j)
            offsets[syms[info>>8][0]]=off
    layout=(sections['.gnu.linkonce.this_module'][5],offsets.get('init_module'),offsets.get('cleanup_module'))
    metadata=[s.decode() for s in data(sections['.modinfo']).split(b'\0') if s]
    vm=next(s for s in metadata if s.startswith('vermagic='))
    imports=sorted({n for n,a in syms if n and a[5]==0 and (a[3]>>4)!=2})
    weak=sorted({n for n,a in syms if n and a[5]==0 and (a[3]>>4)==2})
    return b,layout,vm,imports,weak,sections

p=LAB/'tun/tun.ko'
b,layout,vm,imports,weak,sections=elf(p)
_,ref_layout,ref_vm,_,_,_=elf(LAB.parent/'origin_ko/ccm.ko')
exports=set()
for line in (LAB/'gateway-network-symbols.txt').read_text().splitlines():
    parts=line.split()
    if len(parts)>=3 and re.fullmatch('[0-9a-fA-F]{8}',parts[0]) and parts[2].startswith('__ksymtab_'):
        exports.add(parts[2][len('__ksymtab_'):])
if len(exports)<1000: raise SystemExit('Kernel export snapshot appears incomplete')
missing=sorted(set(imports)-exports)
ok=layout==ref_layout and vm==ref_vm and not missing and '__versions' not in sections
lines=[
    'Module: '+str(p.relative_to(LAB.parent)),
    'SHA256: '+hashlib.sha256(b).hexdigest(),
    vm,
    'Reference layout: '+str(ref_layout),
    'TUN layout: '+str(layout),
    'Kernel export snapshot entries: '+str(len(exports)),
    'Required imports: '+str(len(imports)),
    'Missing exports: '+str(len(missing)),
]
lines += ['MISSING: '+n for n in missing]
lines += ['WEAK OPTIONAL: '+n for n in weak]
lines += ['STATIC_SYMBOL_CHECK_PASS' if ok else 'STATIC_SYMBOL_CHECK_FAIL',
          'Static checks do not prove full network/socket structure compatibility or runtime safety.',
          'No upload, insmod, mknod or network interface operation was performed.']
report='\n'.join(lines)+'\n'
print(report)
(LAB/'tun-static-report.txt').write_text(report)
(LAB/'tun-imports.txt').write_text('\n'.join(imports)+'\n')
raise SystemExit(0 if ok else 1)
