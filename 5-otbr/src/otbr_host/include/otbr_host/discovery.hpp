#pragma once
#include "otbr_host/config.hpp"
#include <openthread/instance.h>
#include <openthread/mdns.h>
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

namespace otbr_host {
// All methods run on the OpenThread owner thread, sharing its mDNS engine.
class ApiDiscovery {
 public:
  ApiDiscovery(otInstance *instance, const Config &config, bool proxy = false);
  ~ApiDiscovery();
  ApiDiscovery(const ApiDiscovery &) = delete;
  ApiDiscovery &operator=(const ApiDiscovery &) = delete;
  void update(const std::string &backbone, bool api_ready);
  void stop();
 private:
  otMdnsService service();
  static void registered(otInstance *, otMdnsRequestId, otError);
  otInstance *instance_;
  const Config &config_;
  std::string mac_, backbone_;
  std::vector<std::uint8_t> txt_;
  std::chrono::steady_clock::time_point next_{};
  unsigned index_{0};
  otMdnsRequestId request_{0};
  bool active_{false};
  bool proxy_{false};
};
}
