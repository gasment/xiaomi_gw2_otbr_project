#include "otbr_host/linux_packet_tap.hpp"
#include "otbr_host/bbr_packet_checksum.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <vector>
#include <arpa/inet.h>
#include <linux/if_packet.h>
#include <linux/if_ether.h>
#include <net/if.h>
#include <net/if_arp.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <unistd.h>

namespace { MiBbrPacketCounters counters{}; }
extern "C" MiBbrPacketCounters mi_bbr_packet_counters() { return counters; }
extern "C" int mi_bbr_packet_check(const char *thread_if, const char *lan_if, int *error) {
  int result = 0;
  {
    ot::Posix::LinuxPacketTap thread, lan;
    const sock_filter drop[] = { BPF_STMT(BPF_RET | BPF_K, 0) };
    if (thread.Open(thread_if, false) != OT_ERROR_NONE) result = errno ? errno : EIO;
    else if (thread.GetDataLinkType() != DLT_NULL) result = ENOTSUP;
    else if (thread.SetFilter(drop, 1) != OT_ERROR_NONE) result = errno ? errno : EIO;
    else if (lan.Open(lan_if, true) != OT_ERROR_NONE) result = errno ? errno : EIO;
    else if (lan.GetDataLinkType() != DLT_EN10MB) result = ENOTSUP;
    else if (lan.SetFilter(drop, 1) != OT_ERROR_NONE) result = errno ? errno : EIO;
  }
  if (error) *error = result;
  return result == 0;
}


namespace ot { namespace Posix {
otError LinuxPacketTap::Open(const char *name, bool see_sent) {
  if (IsOpen()) return OT_ERROR_ALREADY;
  if (!name || std::strlen(name) >= IFNAMSIZ) { errno = EINVAL; return OT_ERROR_INVALID_ARGS; }
  // ETH_P_ALL also sees host-originated LAN traffic. A mandatory kernel BPF
  // program below restricts delivery to IPv6 multicast with scope >= 4.
  int fd = socket(AF_PACKET, SOCK_RAW | SOCK_NONBLOCK | SOCK_CLOEXEC, htons(ETH_P_ALL));
  if (fd < 0) return OT_ERROR_FAILED;
  auto fail = [&](int error, otError result) { close(fd); errno = error; return result; };
  if (fd >= FD_SETSIZE) return fail(EMFILE, OT_ERROR_FAILED);
  ifreq request{}; std::strncpy(request.ifr_name, name, IFNAMSIZ - 1);
  if (ioctl(fd, SIOCGIFINDEX, &request) < 0) return fail(errno, OT_ERROR_FAILED);
  const auto index = static_cast<unsigned>(request.ifr_ifindex);
  if (ioctl(fd, SIOCGIFHWADDR, &request) < 0) return fail(errno, OT_ERROR_FAILED);
  const auto hardware = request.ifr_hwaddr.sa_family;
  const bool tunnel = hardware == ARPHRD_NONE;
  if (!tunnel && hardware != ARPHRD_ETHER) return fail(ENOTSUP, OT_ERROR_NOT_CAPABLE);
  sockaddr_ll address{}; address.sll_family = AF_PACKET;
  address.sll_protocol = htons(ETH_P_ALL); address.sll_ifindex = static_cast<int>(index);
  if (bind(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) < 0) return fail(errno, OT_ERROR_FAILED);
  int auxiliary = 1;
  if (setsockopt(fd, SOL_PACKET, PACKET_AUXDATA, &auxiliary, sizeof(auxiliary)) < 0)
    return fail(errno, OT_ERROR_FAILED);
  fd_ = fd; index_ = index; tunnel_ = tunnel; see_sent_ = see_sent;
  ++counters.open_taps;
  return OT_ERROR_NONE;
}
void LinuxPacketTap::Close() {
  if (fd_ >= 0) { close(fd_); fd_ = -1; --counters.open_taps; }
  index_ = 0;
}
otError LinuxPacketTap::SetFilter(const sock_filter *instructions, std::uint16_t count) {
  if (!IsOpen() || !instructions || !count || count > 64) return OT_ERROR_INVALID_ARGS;
  std::vector<sock_filter> program(instructions, instructions + count);
  // BSD TUN filters count a four-byte AF header; Linux AF_PACKET on TUN starts
  // directly at the IPv6 header. Only absolute loads use those offsets.
  if (tunnel_) for (auto &instruction : program) {
    if ((BPF_CLASS(instruction.code) == BPF_LD || BPF_CLASS(instruction.code) == BPF_LDX) &&
        BPF_MODE(instruction.code) == BPF_ABS) {
      if (instruction.k < 4) return OT_ERROR_INVALID_ARGS;
      instruction.k -= 4;
    }
  }
  sock_fprog filter{}; filter.len = count; filter.filter = program.data();
  return setsockopt(fd_, SOL_SOCKET, SO_ATTACH_FILTER, &filter, sizeof(filter)) == 0 ? OT_ERROR_NONE : OT_ERROR_FAILED;
}
otError LinuxPacketTap::Read(FrameHandler handler, void *context) {
  if (!IsOpen() || !handler) return OT_ERROR_INVALID_ARGS;
  // Bound work per mainloop iteration even under a busy LAN.
  for (unsigned batch = 0; batch < 32; ++batch) {
    std::array<std::uint8_t, 1522> frame{};
    sockaddr_ll from{};
    const unsigned offset = tunnel_ ? 4 : 0;
    iovec vector{frame.data() + offset, frame.size() - offset};
    alignas(cmsghdr) std::array<unsigned char, CMSG_SPACE(sizeof(tpacket_auxdata))> control{};
    msghdr message{}; message.msg_name = &from; message.msg_namelen = sizeof(from);
    message.msg_iov = &vector; message.msg_iovlen = 1;
    message.msg_control = control.data(); message.msg_controllen = control.size();
    const auto length = recvmsg(fd_, &message, MSG_DONTWAIT | MSG_TRUNC);
    if (length < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return OT_ERROR_NONE;
      ++counters.errors; return OT_ERROR_FAILED;
    }
    if (!see_sent_ && from.sll_pkttype == PACKET_OUTGOING) continue;
    if (from.sll_ifindex != static_cast<int>(index_)) continue;
    if (length <= 0 || static_cast<std::size_t>(length) > frame.size() - offset) {
      ++counters.errors; continue;
    }
    bool checksum_pending = false;
    if (message.msg_flags & MSG_CTRUNC) { ++counters.errors; continue; }
    for (auto *item = CMSG_FIRSTHDR(&message); item; item = CMSG_NXTHDR(&message, item)) {
      if (item->cmsg_level == SOL_PACKET && item->cmsg_type == PACKET_AUXDATA &&
          item->cmsg_len >= CMSG_LEN(sizeof(tpacket_auxdata))) {
        tpacket_auxdata auxiliary{}; std::memcpy(&auxiliary, CMSG_DATA(item), sizeof(auxiliary));
        checksum_pending = (auxiliary.tp_status & TP_STATUS_CSUMNOTREADY) != 0;
      }
    }
    if (checksum_pending) {
      const auto link = tunnel_ ? 0u : 14u;
      if (static_cast<std::size_t>(length) <= link ||
          !otbr_host::complete_multicast_checksum(frame.data() + offset + link, length - link)) {
        ++counters.errors; continue;
      }
    }
    if (tunnel_) {
      std::uint32_t family = AF_INET6; std::memcpy(frame.data(), &family, 4);
      ++counters.captured_thread;
    } else ++counters.captured_lan;
    handler(context, frame.data(), static_cast<std::uint16_t>(length + offset));
  }
  return OT_ERROR_NONE;
}
otError LinuxPacketTap::Write(const std::uint8_t *frame, std::uint16_t length) {
  if (!IsOpen() || !frame) return OT_ERROR_INVALID_ARGS;
  sockaddr_ll address{}; address.sll_family = AF_PACKET; address.sll_protocol = htons(ETH_P_IPV6);
  address.sll_ifindex = static_cast<int>(index_);
  if (tunnel_) {
    if (length < 44 || (frame[4] >> 4) != 6) return OT_ERROR_PARSE;
    frame += 4; length -= 4;
  } else {
    if (length < 54 || frame[12] != 0x86 || frame[13] != 0xdd) return OT_ERROR_PARSE;
    address.sll_halen = ETH_ALEN; std::copy_n(frame, ETH_ALEN, address.sll_addr);
  }
  const auto sent = sendto(fd_, frame, length, MSG_DONTWAIT | MSG_NOSIGNAL,
                           reinterpret_cast<sockaddr *>(&address), sizeof(address));
  if (sent != length) { ++counters.errors; return OT_ERROR_FAILED; }
  if (tunnel_) ++counters.injected_thread; else ++counters.injected_lan;
  return OT_ERROR_NONE;
}
}}
