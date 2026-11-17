#pragma once
#include <openthread/instance.h>
#include <chrono>
#include <string>
#include <utility>
namespace otbr_host {
// Owner-thread controller. Probe packet sockets before enabling BBR service,
// including after backbone changes. Ordinary Thread operation remains separate.
class BbrTransport {
 public:
  BbrTransport(otInstance *instance, std::string thread_if) : instance_(instance), thread_if_(std::move(thread_if)) {}
  void update(const std::string &backbone, bool allow);
  void stop();
 private:
  otInstance *instance_;
  std::string thread_if_, backbone_;
  unsigned index_{0};
  bool ready_{false};
  std::chrono::steady_clock::time_point retry_{};
};
}
