"""Validate source adaptation and the real upstream BPF programs; no compiler/socket."""
from pathlib import Path
import hashlib
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
platform=root/'vendor/ot-br-posix/third_party/openthread/repo/src/posix/platform'
names=['multicast_routing.hpp','multicast_routing.cpp','multicast_routing_bpf.cpp']
before={n:hashlib.sha256((platform/n).read_bytes()).hexdigest() for n in names}
def instructions(source,name,tunnel):
    match=re.search(r'const struct sock_filter '+name+r'\[\] = \{(.*?)\n\};',source,re.S)
    assert match,'Upstream filter missing'
    ops=[]
    for line in match.group(1).splitlines():
        code=line.split('//')[0].strip()
        if not code: continue
        m=re.search(r'BPF_(STMT|JUMP)\((.*)\)',code); assert m,code
        args=[x.strip() for x in m.group(2).split(',')]
        expression=args[1].replace(' ','')
        assert re.fullmatch(r'[0-9a-fxA-F+]+',expression)
        number=sum(int(part,0) for part in expression.split('+'))
        op=args[0].replace(' ','')
        if tunnel and op.startswith('BPF_LD|'):
            assert number>=4; number-=4
        ops.append((op,number,int(args[2]) if len(args)>2 else 0,int(args[3]) if len(args)>3 else 0))
    return ops
def accepts(ops,packet):
    pc=0; accumulator=0
    for _ in range(64):
        if pc>=len(ops): return False
        op,k,yes,no=ops[pc]; pc+=1
        if op.startswith('BPF_LD|'):
            size=2 if '|BPF_H|' in op else 1
            if k+size>len(packet): return False
            accumulator=int.from_bytes(packet[k:k+size],'big')
        elif op=='BPF_ALU|BPF_AND|BPF_K': accumulator&=k
        elif op=='BPF_JMP|BPF_JEQ|BPF_K': pc+=yes if accumulator==k else no
        elif op=='BPF_JMP|BPF_JGE|BPF_K': pc+=yes if accumulator>=k else no
        elif op=='BPF_RET|BPF_K': return bool(k)
        else: raise AssertionError(op)
    raise AssertionError('Filter loop')
with tempfile.TemporaryDirectory(prefix='bbr-adapter-check-') as directory:
    subprocess.run(['python3',str(root/'tools/prepare_bbr_userspace.py'),'--output',directory],check=True)
    directory=Path(directory)
    header=(directory/'posix/platform/multicast_routing.hpp').read_text()
    source=(directory/'posix/platform/multicast_routing_bpf.cpp').read_text()
    common=(directory/'posix/platform/multicast_routing.cpp').read_text()
    assert (directory/'posix/platform/infra_if.hpp').is_file()
    assert (directory/'posix/platform/infra_if.cpp').is_file()
    # Exercise the actual CMake remapping block in script mode. No project(),
    # language enable, configure checks or compiler is invoked.
    cmake=(root/'core/bbr_userspace.cmake').read_text()
    start=cmake.index('set(mi_bbr_sources)')
    end=cmake.index('set_property(TARGET openthread-posix PROPERTY SOURCES',start)
    script=directory/'source-map.cmake'
    script.write_text('set(mi_bbr_platform "'+str(platform)+'")\n'
        +'set(mi_bbr_source_dir "'+str(platform)+'")\n'
        +'set(mi_bbr_overlay "'+str(directory)+'")\n'
        +'set(mi_bbr_original_sources multicast_routing.cpp multicast_routing_bpf.cpp infra_if.cpp "'+str(root/'src/infra_adapter.cpp')+'")\n'
        +cmake[start:end]
        +'file(WRITE "'+str(directory/'source-map.txt')+'" "${mi_bbr_sources}")\n')
    subprocess.run(['cmake','-P',str(script)],check=True)
    mapped=(directory/'source-map.txt').read_text().split(';')
    assert mapped[:3]==[str(directory/'posix/platform'/name) for name in ['multicast_routing.cpp','multicast_routing_bpf.cpp','infra_if.cpp']]
    assert mapped[3]==str(root/'src/infra_adapter.cpp')
    assert '-include${mi_bbr_overlay}' not in (root/'core/bbr_userspace.cmake').read_text()
    for name in ['host_main.cpp','bbr_transport.cpp','web_ot.cpp']:
        text=(root/'src'/name).read_text()
        assert 'posix/platform/infra_if.hpp' not in text and 'linux_packet_tap.hpp' not in text
    assert '#include "otbr_host/linux_packet_tap.hpp"' in header
    assert 'LinuxPacketTap' in header and '#include <net/bpf.h>' not in source
    assert 'ReadBackboneMac' in source and 'SIOCGIFHWADDR' in source
    assert 'otIp6SetMulticastPromiscuousEnabled(' not in source
    assert 'aForwardHost = true;' in (platform.parents[1]/'core/net/ip6.cpp').read_text()
    assert '#ifdef __linux__' not in header+common
    assert 'HandleStateChange(gInstance, OT_CHANGED_THREAD_BACKBONE_ROUTER_STATE);' in common
    for tunnel,name in [(True,'kFilterNull'),(False,'kFilterEthernet')]:
        ops=instructions(source,name,tunnel)
        for scope in range(16):
            ip=bytearray(40); ip[0]=0x60; ip[24]=0xff; ip[25]=scope
            packet=bytes(ip) if tunnel else bytes(12)+bytes.fromhex('86dd')+bytes(ip)
            assert accepts(ops,packet)==(scope>=4),(name,scope)
            ip[24]=0xfd
            unicast=bytes(ip) if tunnel else bytes(12)+bytes.fromhex('86dd')+bytes(ip)
            assert not accepts(ops,unicast)
        assert not accepts(ops,b'')
        if not tunnel: assert not accepts(ops,bytes(12)+bytes.fromhex('0800')+bytes(40))
for n in names: assert hashlib.sha256((platform/n).read_bytes()).hexdigest()==before[n]
print('BBR_ADAPTER_STATIC_PASS: source gates, BPF scope/unicast/short-frame rejection and vendor preservation; no compilation or traffic.')
