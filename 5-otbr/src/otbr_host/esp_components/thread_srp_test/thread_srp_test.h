#pragma once
#include "esphome/core/component.h"
#ifdef USE_ESP32
#include <openthread/instance.h>
#include <openthread/ip6.h>
#include <string>

namespace esphome { namespace thread_srp_test {
class ThreadSrpTest : public PollingComponent {
 public:
  void set_server(const std::string &address) { server_text_ = address; }
  void set_port(uint16_t port) { server_.mPort = port; }
  void setup() override;
  void update() override;
  void dump_config() override;
 private:
  std::string server_text_, last_report_;
  otSockAddr server_{};
  otInstance *instance_{nullptr};
  uint32_t last_attempt_{0}, last_wait_log_{0};
  bool started_{false}, attempted_{false};
};
}}
#endif
