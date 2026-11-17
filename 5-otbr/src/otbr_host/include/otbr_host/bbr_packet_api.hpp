#pragma once
#include <cstdint>
// Narrow interface: do not expose OpenThread private C++ headers to OTBR Host.
extern "C" {
struct MiBbrPacketCounters {
  unsigned open_taps;
  std::uint64_t captured_thread, captured_lan;
  std::uint64_t injected_thread, injected_lan, errors;
};
MiBbrPacketCounters mi_bbr_packet_counters();
int mi_bbr_packet_check(const char *thread_if, const char *lan_if, int *error);
}
