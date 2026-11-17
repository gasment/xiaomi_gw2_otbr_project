"""Generate build-local Linux AF_PACKET adapters; never edit locked vendor files."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
platform=root/'vendor/ot-br-posix/third_party/openthread/repo/src/posix/platform'
out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
inputs={name:(platform/name).read_text() for name in ['multicast_routing.hpp','multicast_routing.cpp','multicast_routing_bpf.cpp']}

header=inputs['multicast_routing.hpp']
assert header.count('#ifdef __linux__')==1 and header.count('#ifndef __linux__')==1, 'Unsupported routing header layout'
header=header.replace('#ifndef __linux__','#if !defined(__linux__) || MI_BBR_USERSPACE')
header=header.replace('#ifdef __linux__','#if defined(__linux__) && !MI_BBR_USERSPACE')
header=header.replace('#include "bpf_tap.hpp"','#include "otbr_host/linux_packet_tap.hpp"').replace('BpfTap','LinuxPacketTap')
header=header.replace('#include "openthread-posix-config.h"','#include "openthread-posix-config.h"\n#ifndef MI_BBR_USERSPACE\n#define MI_BBR_USERSPACE 0\n#endif',1)
assert 'kReportIntervalSec = 300' in header
header=header.replace('kReportIntervalSec = 300','kReportIntervalSec = 10')

common=inputs['multicast_routing.cpp']
assert common.count('#ifdef __linux__')>=3, 'Unsupported common routing gates'
common=common.replace('#ifdef __linux__','#if defined(__linux__) && !MI_BBR_USERSPACE')
anchor='    Mainloop::Manager::Get().Add(*this);'
assert common.count(anchor)==1
common=common.replace(anchor,anchor+'\n    // Rebind after an infrastructure switch even if Primary BBR state stayed the same.\n    HandleStateChange(gInstance, OT_CHANGED_THREAD_BACKBONE_ROUTER_STATE);',1)

userspace=inputs['multicast_routing_bpf.cpp']
gate='#if OPENTHREAD_POSIX_CONFIG_BACKBONE_ROUTER_MULTICAST_ROUTING_ENABLE && !defined(__linux__)'
assert userspace.count(gate)==1
userspace=userspace.replace(gate,'#if OPENTHREAD_POSIX_CONFIG_BACKBONE_ROUTER_MULTICAST_ROUTING_ENABLE && defined(__linux__) && MI_BBR_USERSPACE')
userspace=userspace.replace('#include <net/bpf.h>','#include <linux/filter.h>\n#include <net/if_arp.h>')
userspace=userspace.replace('#include <net/if_dl.h>','#include <sys/ioctl.h>')
userspace=userspace.replace('struct bpf_insn','struct sock_filter')
# This locked core always forwards multicast to Host in Ip6::DetermineAction.
# Do not add the removed otIp6SetMulticastPromiscuousEnabled API. Reject a
# changed core contract here instead of silently losing Thread-to-LAN traffic.
ip6=(platform.parents[1]/'core/net/ip6.cpp').read_text()
contract='// Always forward multicast packets to host network stack'
assert contract in ip6, 'Re-audit core multicast-to-Host delivery'
assert 'aForwardHost = true;' in ip6[ip6.index(contract):ip6.index(contract)+150]
begin=userspace.index('otError MulticastRoutingManager::ReadBackboneMac(void)')
end=userspace.index('otError MulticastRoutingManager::OpenBackboneTap(void)',begin)
userspace=userspace[:begin]+'''otError MulticastRoutingManager::ReadBackboneMac(void)
{
    const char *name = otSysGetInfraNetifName();
    if (name == nullptr || name[0] == '\\0') { errno = ENODEV; return OT_ERROR_NOT_FOUND; }
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return OT_ERROR_FAILED;
    struct ifreq request = {};
    strncpy(request.ifr_name, name, sizeof(request.ifr_name) - 1);
    int result = ioctl(fd, SIOCGIFHWADDR, &request);
    int savedErrno = errno;
    close(fd);
    if (result != 0) { errno = savedErrno; return OT_ERROR_FAILED; }
    if (request.ifr_hwaddr.sa_family != ARPHRD_ETHER) { errno = ENOTSUP; return OT_ERROR_NOT_CAPABLE; }
    memcpy(mBackboneMac, request.ifr_hwaddr.sa_data, kMacSize);
    return OT_ERROR_NONE;
}

'''+userspace[end:]
assert '#include <net/bpf.h>' not in userspace and 'sockaddr_dl' not in userspace

dest=out/'posix/platform'
# Quoted sibling includes must see one coherent private header tree. Compile
# the POSIX sources from this build-local copy instead of forcing a header into
# unrelated Host translation units. Preserve the locked checkout verbatim.
shutil.copytree(platform, dest, dirs_exist_ok=True)
(dest/'multicast_routing.hpp').write_text(header)
(dest/'multicast_routing.cpp').write_text(common)
(dest/'multicast_routing_bpf.cpp').write_text(userspace)
receipt={'upstream_sha256':{name:hashlib.sha256(data.encode()).hexdigest() for name,data in inputs.items()},
         'backend':'experimental-linux-af-packet','vendor_files_modified':False}
(out/'adapter-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('BBR_USERSPACE_ADAPTER_GENERATED:',out)
