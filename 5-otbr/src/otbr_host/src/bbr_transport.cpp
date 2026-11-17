#include "otbr_host/bbr_transport.hpp"
#if defined(MI_BBR_USERSPACE) && MI_BBR_USERSPACE
#include "otbr_host/bbr_packet_api.hpp"
#include <openthread/backbone_router_ftd.h>
#include <net/if.h>
#include <cerrno>
#include <cstring>
#include <iostream>

namespace otbr_host {
void BbrTransport::stop() {
  otBackboneRouterSetEnabled(instance_, false);
  ready_ = false; index_ = 0; backbone_.clear();
}
void BbrTransport::update(const std::string &backbone, bool allow) {
  const auto index = backbone.empty() ? 0 : if_nametoindex(backbone.c_str());
  if (!allow || !index) { if (ready_) stop(); return; }
  if (ready_ && index_ == index && backbone_ == backbone) return;
  if (ready_ && (index_ != index || backbone_ != backbone)) { stop(); retry_ = {}; }
  const auto now = std::chrono::steady_clock::now();
  if (now < retry_) return;
  if (ready_) stop();
  retry_ = now + std::chrono::seconds(5);
  int error = 0;
  if (!mi_bbr_packet_check(thread_if_.c_str(), backbone.c_str(), &error)) {
    std::cerr << "[bbr] Packet backend unavailable on " << backbone << ": " << std::strerror(error)
              << "; BBR remains disabled, retrying in 5s\n";
    return;
  }
  backbone_ = backbone; index_ = index; ready_ = true;
  otBackboneRouterSetEnabled(instance_, true);
  std::cerr << "[bbr] BBR_BACKEND=userspace-af-packet ready on " << backbone
            << "; enabled as candidate, Primary election stays with Thread\n";
}
}
#else
namespace otbr_host {
void BbrTransport::update(const std::string &, bool) {}
void BbrTransport::stop() {}
}
#endif
