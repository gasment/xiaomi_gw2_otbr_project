#pragma once
#include <cstdint>
#include <linux/filter.h>
#include <openthread/error.h>
#include "core/common/non_copyable.hpp"

// Match the two upstream BPF link types; Linux's raw TUN tap is adapted to
// DLT_NULL at this boundary, so upstream multicast policy stays unchanged.
#ifndef DLT_NULL
#define DLT_NULL 0
#endif
#ifndef DLT_EN10MB
#define DLT_EN10MB 1
#endif

#include "otbr_host/bbr_packet_api.hpp"

namespace ot { namespace Posix {
class LinuxPacketTap : private NonCopyable {
 public:
  using FrameHandler = void (*)(void *, const std::uint8_t *, std::uint16_t);
  ~LinuxPacketTap() { Close(); }
  otError Open(const char *name, bool see_sent);
  void Close();
  bool IsOpen() const { return fd_ >= 0; }
  int GetFd() const { return fd_; }
  unsigned GetIfIndex() const { return index_; }
  std::uint32_t GetDataLinkType() const { return tunnel_ ? DLT_NULL : DLT_EN10MB; }
  otError SetFilter(const sock_filter *instructions, std::uint16_t count);
  otError Read(FrameHandler handler, void *context);
  otError Write(const std::uint8_t *frame, std::uint16_t length);
 private:
  int fd_{-1};
  unsigned index_{0};
  bool tunnel_{false}, see_sent_{false};
};
}}
